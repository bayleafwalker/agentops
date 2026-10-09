import hashlib,json,runpy
from importlib.metadata import version
from pathlib import Path
expected={'vuoro-service':'0.1.90','sprintctl':'0.16.0','auditctl':'0.1.9','vuoro-adapter-kit':'0.2.0','vuoro-schema-runtime':'0.1.0'}
actual={name:version(name) for name in expected}
assert actual==expected,actual
print(actual)
manifest=Path('/opt/vuoro/composition/adapter-pins.json')
attested=json.loads(Path('/opt/vuoro/composition/installed-composition.json').read_text())
assert attested['verified'] is True
assert attested['manifest_sha256']==hashlib.sha256(manifest.read_bytes()).hexdigest()
checker=runpy.run_path('/usr/local/bin/attest-installed-composition')
for entry in attested['distributions']:
 wheel=Path('/opt/vuoro/adapters')/entry['artifact_url'].rsplit('/',1)[-1]
 assert hashlib.sha256(wheel.read_bytes()).hexdigest()==entry['artifact_sha256']
 assert checker['_installed_files_digest'](entry['distribution'])==(entry['installed_files_sha256'],entry['installed_files_count'])
from sprintctl.vuoro_adapter import register_work_catalog
from auditctl.vuoro_adapter import VuoroAuditAdapter
from vuoro_service.catalog import CatalogRegistry
class WorkStub:
 @staticmethod
 def maintenance_resource_schema_available():return False
registry=CatalogRegistry();register_work_catalog(registry,WorkStub());VuoroAuditAdapter(connection_factory=lambda:None).register(registry)
catalog=registry.catalog().model_dump(mode='json')
assert len(catalog['operations'])==79
assert registry.revision=='29c2dd503c4de2347fd1ba481b23a80b5465e791ce64a5ba8e8b37c2f8185090'
assert sum(op['name']=='work.effect.propose-bound-v1' for op in catalog['operations'])==1
print('actual installed files, pinned wheels and resource-disabled catalog79 verified')

assert sum(op['name']=='work.evidence.evaluate-v1' for op in catalog['operations'])==1
print('actual digest-pulled image includes evaluator exactlyonce')
