\set ON_ERROR_STOP on

BEGIN;

INSERT INTO identity_access.users (email, account_type, username, status)
VALUES ('manager@example.com', 'staff', 'Manager', 'active');

INSERT INTO identity_access.staff (
    user_id, role_id, staff_code, display_name, employment_status
)
SELECT u.id, r.id, 'MGR-001', 'Manager', 'active'
FROM identity_access.users AS u
CROSS JOIN identity_access.roles AS r
WHERE u.email = 'manager@example.com'
  AND r.code = 'manager_admin';

INSERT INTO identity_access.users (email, account_type, username, status)
VALUES ('tenant@example.com', 'customer', 'Tenant', 'active');

INSERT INTO identity_access.customer_profiles (user_id)
SELECT id FROM identity_access.users WHERE email = 'tenant@example.com';

DO $$
BEGIN
    BEGIN
        INSERT INTO identity_access.users (email, account_type, username)
        VALUES ('manager@example.com', 'customer', 'Duplicate');
        RAISE EXCEPTION 'duplicate email was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO identity_access.users (email, account_type, username)
        VALUES ('Mixed@Example.com', 'customer', 'Mixed');
        RAISE EXCEPTION 'non-normalized email was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END
$$;

DO $$
DECLARE blocked boolean := false;
BEGIN
    BEGIN
        UPDATE identity_access.users
        SET email = 'changed@example.com'
        WHERE email = 'manager@example.com';
    EXCEPTION WHEN raise_exception THEN
        blocked := true;
    END;
    IF NOT blocked THEN
        RAISE EXCEPTION 'email change was accepted';
    END IF;
END
$$;

DO $$
DECLARE blocked boolean := false;
BEGIN
    BEGIN
        UPDATE identity_access.users
        SET account_type = 'customer'
        WHERE email = 'manager@example.com';
    EXCEPTION WHEN raise_exception THEN
        blocked := true;
    END;
    IF NOT blocked THEN
        RAISE EXCEPTION 'account type change was accepted';
    END IF;
END
$$;

DO $$
DECLARE blocked boolean := false;
BEGIN
    BEGIN
        INSERT INTO identity_access.staff (
            user_id, role_id, staff_code, display_name
        )
        SELECT u.id, r.id, 'BAD-001', 'Bad profile'
        FROM identity_access.users AS u
        CROSS JOIN identity_access.roles AS r
        WHERE u.email = 'tenant@example.com'
          AND r.code = 'maintainer';
    EXCEPTION WHEN raise_exception THEN
        blocked := true;
    END;
    IF NOT blocked THEN
        RAISE EXCEPTION 'customer account was accepted as staff';
    END IF;
END
$$;

INSERT INTO identity_access.auth_sessions (user_id, last_seen_at, expires_at)
SELECT id, now(), now() + interval '1 day'
FROM identity_access.users
WHERE email = 'manager@example.com';

INSERT INTO identity_access.refresh_tokens (
    session_id, family_id, token_hash, issued_at, expires_at
)
SELECT id, gen_random_uuid(), 'token-hash-1', now(), now() + interval '30 days'
FROM identity_access.auth_sessions;

DO $$
BEGIN
    BEGIN
        INSERT INTO identity_access.refresh_tokens (
            session_id, family_id, token_hash, issued_at, expires_at
        )
        SELECT id, gen_random_uuid(), 'token-hash-2', now(), now() + interval '30 days'
        FROM identity_access.auth_sessions;
        RAISE EXCEPTION 'second active refresh token was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END
$$;

INSERT INTO staff_agent.staff_sessions (staff_id, title, last_message_at)
SELECT public_id, 'Test session', now()
FROM identity_access.staff
WHERE staff_code = 'MGR-001';

INSERT INTO staff_agent.staff_messages (
    session_id, sequence_no, role, content, status, client_message_id
)
SELECT id, 1, 'user', 'Inspect unit A', 'completed', gen_random_uuid()
FROM staff_agent.staff_sessions
WHERE title = 'Test session';

INSERT INTO staff_agent.staff_requests (
    session_id, trigger_message_id, original_text, idempotency_key, policy_version
)
SELECT s.id, m.id, m.content, gen_random_uuid(), 'v1'
FROM staff_agent.staff_sessions AS s
JOIN staff_agent.staff_messages AS m ON m.session_id = s.id
WHERE s.title = 'Test session'
  AND m.sequence_no = 1;

UPDATE staff_agent.staff_messages AS m
SET request_id = r.id
FROM staff_agent.staff_requests AS r
WHERE m.id = r.trigger_message_id;

INSERT INTO staff_agent.staff_messages (
    session_id, request_id, sequence_no, role, kind, content, status
)
SELECT session_id, id, 2, 'assistant', 'clarification', 'Which date?', 'completed'
FROM staff_agent.staff_requests;

INSERT INTO staff_agent.staff_clarifications (
    request_id, ordinal, question_message_id, status
)
SELECT r.id, 1, m.id, 'open'
FROM staff_agent.staff_requests AS r
JOIN staff_agent.staff_messages AS m
  ON m.request_id = r.id AND m.sequence_no = 2;

DO $$
BEGIN
    BEGIN
        INSERT INTO staff_agent.staff_clarifications (
            request_id, ordinal, question_message_id, status
        )
        SELECT r.id, 2, m.id, 'open'
        FROM staff_agent.staff_requests AS r
        JOIN staff_agent.staff_messages AS m
          ON m.request_id = r.id AND m.sequence_no = 2;
        RAISE EXCEPTION 'second open clarification was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END
$$;

SELECT 'database invariants passed' AS result;

ROLLBACK;
