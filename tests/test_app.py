"""Self-contained endpoint and scoring tests. Run: python -m unittest discover -s tests -v"""
import importlib, os, sys, tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient

class JobPilotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  os.environ['JOBPILOT_DATA_DIR']=cls.temp.name
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
  sys.modules.pop('app',None)
  cls.module=importlib.import_module('app')
  cls.client=TestClient(cls.module.app)
  cls.client.put('/api/profile',json={'values':{'education_level':'ged'}})
  cls.client.put('/api/config',json={'values':{'location':'Austin, TX','location_confirmed':True,'location_aliases':'Round Rock, TX'}})
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()

 def test_bootstrap_sliders_and_defaults(self):
  r=self.client.get('/api/bootstrap');self.assertEqual(r.status_code,200)
  data=r.json();self.assertEqual(len(data['sliders']),27)
  self.assertFalse(data['config']['auto_submit_enabled'])

 def test_demo_cannot_be_submitted(self):
  self.client.post('/api/jobs/demo')
  job=next(x for x in self.client.get('/api/jobs').json()['jobs'] if x['sample'])
  r=self.client.patch('/api/jobs/'+job['id'],json={'status':'approved'})
  self.assertEqual(r.status_code,400)
  self.client.delete('/api/jobs/demo')

 def test_manual_job_and_pipeline(self):
  payload={'company':'Unit Test Employer','title':'Junior Customer Service Associate','url':'https://example.org/real-posting-for-tests','location':'Austin, TX','salary':'$23/hour','description':'entry level customer service'}
  self.assertEqual(self.client.post('/api/jobs/manual',json=payload).status_code,200)
  rows=self.client.get('/api/jobs').json()['jobs'];self.assertEqual(len(rows),1)
  job=rows[0];self.assertGreater(job['score'],55)
  self.assertEqual(self.client.post('/api/jobs/'+job['id']+'/apply').status_code,400)
  self.assertEqual(self.client.patch('/api/jobs/'+job['id'],json={'status':'saved'}).status_code,200)
  self.assertEqual(self.client.patch('/api/jobs/'+job['id'],json={'status':'approved'}).status_code,200)
  self.assertEqual(self.client.post('/api/jobs/'+job['id']+'/apply').status_code,400) # no profile
  self.assertEqual(self.client.patch('/api/jobs/'+job['id'],json={'status':'applied'}).status_code,200)
  self.assertEqual(self.client.get('/api/bootstrap').json()['stats']['applied'],1)

 def test_settings_recalculate_and_validate(self):
  v={'target_hourly':36,'weight_pay':100,'min_weekly_hours':999,'remote_preference':75}
  r=self.client.put('/api/config',json={'values':v});self.assertEqual(r.status_code,200)
  self.assertEqual(r.json()['config']['min_weekly_hours'],60)
  self.assertEqual(r.json()['config']['target_hourly'],36)
  r=self.client.get('/api/jobs');self.assertEqual(len(r.json()['jobs']),1)

 def test_profile_not_allowed_to_set_resume_path(self):
  r=self.client.put('/api/profile',json={'values':{'first_name':'Example','resume_path':'/tmp/malicious'}})
  self.assertEqual(r.status_code,200)
  self.assertEqual(r.json()['profile']['first_name'],'Example')
  self.assertEqual(r.json()['profile']['resume_path'],'')

 def test_csv_and_url_validation(self):
  self.assertIn('company,title,location',self.client.get('/api/export.csv').text)
  r=self.client.post('/api/jobs/manual',json={'company':'Test','title':'Title','url':'javascript:alert(1)'})
  self.assertEqual(r.status_code,400)

if __name__=='__main__':unittest.main()
