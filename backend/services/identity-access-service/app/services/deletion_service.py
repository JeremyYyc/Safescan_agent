from uuid import UUID

from safescan_common.http.errors import ApiError, conflict, forbidden, not_found, unauthorized
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import deletion_peppers, subject_fingerprint, verify_password
from app.domain.principal import Principal
from app.mappers.audit_mapper import AuditMapper
from app.mappers.auth_mapper import AuthMapper
from app.mappers.deletion_mapper import DeletionMapper
from app.mappers.user_mapper import UserMapper
from app.services.deletion_client import DeletionBlockers, DeletionEligibilityClient


REQUIRED_DELETION_SERVICES = ("property-leasing", "maintenance", "inspection-report")


class DeletionService:
    def __init__(self, session: Session, settings: Settings,
                 eligibility: DeletionEligibilityClient | None = None) -> None:
        self.session = session
        self.settings = settings
        self.users = UserMapper(session)
        self.auth = AuthMapper(session)
        self.audit = AuditMapper(session)
        self.deletions = DeletionMapper(session)
        self.eligibility = eligibility or DeletionEligibilityClient(settings)

    @staticmethod
    def view(request: dict, acknowledgements: list[dict] | None = None) -> dict:
        return {
            "id": str(request["public_id"]),
            "status": request["status"],
            "blockers": request["blocker_summary"],
            "acknowledgements": [
                {"service": row["service"], "status": row["status"], "attempt": row["attempt"]}
                for row in (acknowledgements or [])
            ],
            "created_at": request["created_at"],
            "updated_at": request["updated_at"],
        }

    @staticmethod
    def _raise_blocker(blockers: DeletionBlockers) -> None:
        if blockers.leases:
            raise conflict("active_lease_blocks_deletion", "An active lease blocks account deletion",
                           blocker_count=len(blockers.leases), lease_ids=list(blockers.leases))
        if blockers.maintenance_orders:
            raise conflict("open_maintenance_orders_block_deletion",
                           "Open maintenance orders block account deletion",
                           blocker_count=len(blockers.maintenance_orders),
                           order_ids=list(blockers.maintenance_orders))

    def request(self, principal: Principal, *, current_password: str, reason: str | None,
                version: int, idempotency_key: str, correlation_id: UUID) -> dict:
        if principal.account_type != "customer":
            raise forbidden("action_forbidden", "Staff accounts cannot be self-deleted")
        existing = self.deletions.get_for_user(principal.user_id)
        if existing:
            if existing["idempotency_key"] == idempotency_key and existing["reason"] != reason:
                raise conflict("idempotency_conflict", "Idempotency key was used with another request",
                               operation="delete_account")
            return self.view(dict(existing), self.deletions.acknowledgements(existing["id"]))
        user = self.users.get_by_internal_id(principal.user_id, for_update=True)
        credential = self.users.get_password(principal.user_id, for_update=True)
        if not user or not credential or not verify_password(credential["secret_hash"], current_password):
            self.session.rollback()
            raise unauthorized("invalid_credentials", "Current password is invalid")
        if user["version"] != version:
            self.session.rollback()
            raise conflict("version_conflict", "Account was changed by another request",
                           current_version=user["version"])
        if user["status"] != "active":
            self.session.rollback()
            raise conflict("account_deletion_pending", "Account deletion is already pending",
                           current_status=user["status"])
        self.session.rollback()

        first_check = self.eligibility.check(principal.subject)
        self._raise_blocker(first_check)

        try:
            user = self.users.get_by_internal_id(principal.user_id, for_update=True)
            existing = self.deletions.get_for_user(principal.user_id, for_update=True)
            if existing:
                self.session.rollback()
                if existing["idempotency_key"] == idempotency_key and existing["reason"] != reason:
                    raise conflict("idempotency_conflict",
                                   "Idempotency key was used with another request",
                                   operation="delete_account")
                return self.view(dict(existing), self.deletions.acknowledgements(existing["id"]))
            if not user or user["status"] != "active" or user["version"] != version:
                self.session.rollback()
                raise conflict("version_conflict", "Account was changed by another request")
            request = self.deletions.create(
                user_id=user["id"], subject_id=user["public_id"], reason=reason,
                idempotency_key=idempotency_key, required_services=list(REQUIRED_DELETION_SERVICES),
            )
            self.users.update_user_status(user["id"], status="deletion_pending", version=version)
            self.auth.revoke_all_for_user(user["id"], "account_deletion_pending")
            self.audit.add("account_deletion_requested", correlation_id=correlation_id,
                           user_id=user["id"], details={"request_id": str(request["public_id"])})
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.deletions.get_for_user(principal.user_id)
            if existing:
                return self.view(dict(existing), self.deletions.acknowledgements(existing["id"]))
            raise

        try:
            second_check = self.eligibility.check(principal.subject)
        except ApiError as exc:
            if exc.code in {
                "active_lease_blocks_deletion",
                "open_maintenance_orders_block_deletion",
            }:
                request = self.deletions.set_status(
                    request["id"], "blocked", blockers={"code": exc.code, **exc.details}
                )
                self.session.commit()
                return self.view(request)
            return self.view(request)
        if second_check.any:
            blockers = {
                "lease_ids": list(second_check.leases),
                "order_ids": list(second_check.maintenance_orders),
            }
            request = self.deletions.set_status(request["id"], "blocked", blockers=blockers)
        else:
            request = self.deletions.set_status(request["id"], "processing", blockers={})
            self.deletions.publish_requested(request, correlation_id)
        self.session.commit()
        return self.view(request)

    def acknowledge(self, principal: Principal, request_public_id: UUID, *, service: str,
                    status: str, details: dict) -> dict:
        caller = principal.subject.removeprefix("service:")
        if caller != service or service not in REQUIRED_DELETION_SERVICES:
            raise forbidden("action_forbidden", "Service may only acknowledge its own deletion work")
        request = self.deletions.get(request_public_id, for_update=True)
        if not request:
            raise not_found("resource_not_found", "Deletion request was not found")
        if request["status"] == "completed":
            return {"accepted": False, "duplicate": True, "completed": True}
        _, duplicate = self.deletions.acknowledge(
            request_id=request["id"], service=service, status=status, details=details
        )
        acknowledgements = self.deletions.acknowledgements(request["id"])
        by_service = {row["service"]: row["status"] for row in acknowledgements}
        if status == "failed":
            self.deletions.set_status(request["id"], "failed")
        completed = all(by_service.get(name) == "completed" for name in REQUIRED_DELETION_SERVICES)
        if completed:
            _, pepper = deletion_peppers(self.settings)[0]
            fingerprint = subject_fingerprint(str(request["subject_id"]), pepper)
            self.deletions.finalize(
                dict(request), fingerprint=fingerprint,
                fingerprint_version=self.settings.deletion_pepper_version,
            )
        self.session.commit()
        return {"accepted": not duplicate, "duplicate": duplicate, "completed": completed}

    def status(self, request_public_id: UUID) -> dict:
        request = self.deletions.get(request_public_id)
        if not request:
            raise not_found("resource_not_found", "Deletion request was not found")
        return self.view(dict(request), self.deletions.acknowledgements(request["id"]))

    def tombstone_check(self, subject_id: UUID) -> dict:
        fingerprints = [
            subject_fingerprint(str(subject_id), pepper)
            for _, pepper in deletion_peppers(self.settings)
        ]
        row = self.deletions.tombstone_exists(fingerprints)
        return {"deleted": row is not None,
                "deletion_completed_at": row["completed_at"] if row else None}
