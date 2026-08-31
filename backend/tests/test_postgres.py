"""Run against an isolated database: TEST_DATABASE_URL=... pytest."""
import os
from uuid import uuid4
import pytest
from sqlalchemy.exc import IntegrityError
from app.settings import get_settings
from app.persistence.database import get_engine, get_connection
from app import db

@pytest.fixture(autouse=True)
def database(monkeypatch):
    url=os.environ.get('TEST_DATABASE_URL')
    if not url: pytest.skip('TEST_DATABASE_URL is required for PostgreSQL integration')
    monkeypatch.setenv('DATABASE_URL',url)
    monkeypatch.setenv('AUTH_SECRET','isolated-test-auth-secret')
    monkeypatch.setenv('PUBLIC_ID_SECRET','isolated-test-public-secret')
    get_settings.cache_clear();get_engine.cache_clear()
    yield
    get_engine().dispose();get_engine.cache_clear();get_settings.cache_clear()

def user(): return db.create_user(uuid4().hex+'@test.invalid','tester','test-password')

def test_auth_chat_and_messages():
    u=user(); assert u['password'].startswith('scrypt$')
    assert db.verify_user(u['email'].upper(),'test-password')
    assert db.verify_user(u['email'],'wrong') is None
    c=db.create_chat('Test',u['user_id']);chat=db.get_chat(c)
    assert chat['id'].startswith('m8_')
    assert db.resolve_chat_internal_id(chat['id']) == c
    assert db.update_chat_metadata(c,pinned=True)['pinned'] is True
    m=db.add_chat_message(c,'user','hi',u['user_id'],{'intent':'GUIDE'})
    assert m and db.get_chat_messages(c)[0]['meta']=={'intent':'GUIDE'}
    assert db.get_recent_user_questions(c)==['hi']
    assert db.list_chats(u['user_id'])
    assert db.delete_chat(c)

def test_reports_pdfs_and_refs():
    u=user();c=db.create_chat('Kitchen',u['user_id']);bot=db.create_chat('Bot',u['user_id'],'bot')
    r=db.store_report([{'name':'Kitchen'}],'/test/'+uuid4().hex+'.mp4',{'title':'Kitchen','regions':[]},[],c,u['user_id'])
    assert db.add_chat_report_detail(c,r,u['user_id'])
    report=db.get_report(r)
    assert db.resolve_report_internal_id(report['report_id'])==r
    assert report['region_info']==[{'name':'Kitchen'}]
    assert db.search_reports_by_chat_title(u['user_id'],'kitchen')
    assert db.add_chat_report_ref(bot,r,c)
    assert db.add_chat_report_ref(bot,r,c)
    assert len(db.list_chat_report_refs(bot))==1
    assert db.get_active_report_payloads_for_chat(bot)
    p=db.store_pdf_report(user_id=u['user_id'],source_path='/test/'+uuid4().hex+'.pdf',title='PDF',origin_chat_id=c,derived_from_report_id=r,pdf_kind='exported')
    db.add_chat_report_ref(c,p,c)
    assert db.get_latest_pdf_for_chat(c)
    assert db.delete_pdf_report_and_refs(p,u['user_id'])
    assert db.delete_chat(c)
    assert db.list_chat_report_refs(bot)[0]['status']=='deleted'

def test_unique_foreign_key_and_rollback():
    u=user()
    with pytest.raises(IntegrityError): db.create_user(u['email'],'duplicate','pw')
    with pytest.raises(IntegrityError): db.create_chat('orphan',9223372036854775806)
    with pytest.raises(RuntimeError):
        with get_connection():
            c=db.create_chat('rollback',u['user_id'])
            db.add_chat_message(c,'user','must rollback',u['user_id'])
            raise RuntimeError('injected failure')
    assert db.get_chat(c) is None

def test_report_multi_table_rollback(monkeypatch):
    from app.persistence import repositories
    u=user();c=db.create_chat('rollback',u['user_id'])
    def fail(*args): raise RuntimeError('injected asset failure')
    monkeypatch.setattr(repositories,'_replace_report_assets',fail)
    with pytest.raises(RuntimeError): db.store_report([], '/test/video.mp4',{},[],c,u['user_id'])
    assert db.get_latest_report_id(c) is None

def test_api_auth_and_ownership():
    from fastapi.testclient import TestClient
    from main import app
    client=TestClient(app)
    payload={'email':uuid4().hex+'@test.invalid','username':'API','password':'test-pass'}
    response=client.post('/api/auth/register',json=payload)
    assert response.status_code==200,response.text
    headers={'Authorization':'Bearer '+response.json()['token']}
    assert client.post('/api/auth/login',json=payload).status_code==200
    assert client.get('/api/chats',headers=headers).status_code==200
    assert client.get('/api/chats').status_code==401
