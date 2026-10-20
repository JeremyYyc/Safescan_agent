import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from export_sql_delivery import literal, insert, OUT
from upload_dataset_minio import validated_objects, upload


class Missing(Exception):
    code = 'NoSuchKey'


class Response(io.BytesIO):
    def stream(self, size):
        while chunk := self.read(size):
            yield chunk

    def release_conn(self):
        pass


class Client:
    def __init__(self, existing=None):
        self.existing=existing
        self.puts=[]

    def bucket_exists(self, bucket):
        return True

    def stat_object(self, bucket, key):
        if self.existing is None:
            raise Missing()
        return SimpleNamespace(size=len(self.existing))

    def get_object(self, bucket, key):
        return Response(self.existing)

    def fput_object(self, bucket, key, path, **kwargs):
        self.puts.append((bucket,key))


class DeliveryTests(unittest.TestCase):
    def fixture(self, folder):
        body=b'test image bytes'
        (folder/'sample.jpg').write_bytes(body)
        row={'sha256':hashlib.sha256(body).hexdigest(),'local_path':'sample.jpg',
             'bucket':'safescan-media','object_key':'datasets/test/sample.jpg',
             'byte_size':len(body),'content_type':'image/jpeg'}
        (folder/'objects.json').write_text(json.dumps([row]),encoding='utf-8')
        return row,body

    def test_sql_literals(self):
        self.assertEqual(literal("O'Brien\\door\nline"),"'O''Brien\\door\nline'")
        self.assertEqual(literal(None),'NULL')
        self.assertEqual(literal(False),'FALSE')
        with self.assertRaises(ValueError):
            literal('bad\x00text')
        self.assertIn('DO NOTHING',insert('x',['id'],['1'],['id']))

    def test_upload_new_and_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            row,body=self.fixture(root)
            client=Client()
            upload(root,client,Missing)
            self.assertEqual(client.puts,[(row['bucket'],row['object_key'])])
            client=Client(body)
            upload(root,client,Missing)
            self.assertEqual(client.puts,[])

    def test_existing_conflict_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            client=Client(b'other bytes')
            with self.assertRaises(RuntimeError):
                upload(root,client,Missing)
            self.assertEqual(client.puts,[])

    def test_corruption_and_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            row,_=self.fixture(root)
            (root/'sample.jpg').write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                validated_objects(root)
            row['local_path']='../outside.jpg'
            (root/'objects.json').write_text(json.dumps([row]),encoding='utf-8')
            with self.assertRaises(ValueError):
                validated_objects(root)

    def test_exported_counts_and_object_keys(self):
        objects=validated_objects(OUT)
        self.assertEqual(len(objects),339)
        sql=(OUT/'dataset.sql').read_text(encoding='utf-8')
        for table,n in [('housing_records',58),('repair_cases',59),('media_assets',339),
                        ('housing_media',265),('repair_media',75),('knowledge_documents',11),('knowledge_steps',62)]:
            self.assertEqual(sql.count(f'INSERT INTO collected_data.{table} ('),n,table)
        for obj in objects:
            self.assertIn(literal(obj['object_key']),sql)
            self.assertIn(literal(obj['bucket']),sql)
        self.assertNotIn('DROP TABLE',sql)
        self.assertNotIn('TRUNCATE',sql)


if __name__=='__main__':
    unittest.main()
