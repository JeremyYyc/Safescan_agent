#!/usr/bin/env python3
"""Verify the city staffing extension against the local demo through Gateway."""
import importlib.util,sys,json
from pathlib import Path
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,Path(path));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def main(base):
    identity=load('identity_smoke',Path(__file__).with_name('identity-api-smoke.py'))
    identity.verify_staff_logins_and_logout(base)
    portal=load('portal_smoke',Path(__file__).with_name('portal-bff-api-smoke.py'));request,expect=portal.request,portal.expect
    summary={'staff_logins':16,'maintainer_orders':{}}
    tokens={};orders={}
    for first,last,city,count in [('Mason','Lewis','adelaide',29),('Benjamin','Scott','perth',12)]:
        data=expect(request(base,'POST','/api/v1/auth/login',payload={'email':f'{first}Safescan@outlook.com','password':f'staff{first}{last}123456'}),200)['data']
        token=data['access_token'];staff=data['user']['staff'];assert staff['city_id']==city
        token_id=staff['id'];result=expect(request(base,'GET','/api/v1/staff/maintenance-orders?status=assigned&limit=100',token=token),200)['data']['items']
        assert len(result)==count,(city,len(result))
        assert all(r['assigned_staff']['id']==token_id for r in result)
        tokens[city]=token;orders[city]=result
        summary['maintainer_orders'][city]=len(result)
    assert request(base,'GET','/api/v1/staff/maintenance-orders/'+orders['perth'][0]['id'],token=tokens['adelaide']).status==404
    consultant=expect(request(base,'POST','/api/v1/auth/login',payload={'email':'LucasSafescan@outlook.com','password':'staffLucasAnderson123456'}),200)['data']
    result=expect(request(base,'GET','/api/v1/staff/properties?limit=100',token=consultant['access_token']),200)['data']['items']
    assert len(result)==34 and all(p['city_id']=='perth' for p in result)
    summary['perth_consultant_properties']=len(result);summary['cross_city_work_order_access']='denied'
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8080')
