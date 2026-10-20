"""Per-user canonical mappings keyed by reviewed source identity and profile."""
import json
from pathlib import Path
from app_output import output_path


class MappingTemplates:
    def __init__(self,path=None):
        self.path=Path(path) if path else output_path('engineering-channel-mappings.json','templates');self.profiles={};self.units={};self.warning=''
        if self.path.exists():
            try:
                record=json.loads(self.path.read_text(encoding='utf-8'))
                if record.get('version')!=1 or not isinstance(record.get('profiles'),dict):raise ValueError('Unsupported canonical mapping template')
                if any(not isinstance(v,dict) or any(x is not None and not isinstance(x,str) for x in v.values()) for v in record['profiles'].values()):raise ValueError('Invalid canonical mapping')
                units=record.get('source_units',{})
                from app_engineering_units import UNITS,unit
                if not isinstance(units,dict) or any(not isinstance(group,dict) or any(not isinstance(value,str) or unit(value) not in UNITS for value in group.values()) for group in units.values()):raise ValueError('Invalid confirmed source units')
                self.profiles=record['profiles'];self.units=units
            except (OSError,ValueError,TypeError) as exc:self.warning=str(exc)

    def get(self,profile):
        allowed={c['id'] for c in profile['channels']}
        return {key:value for key,value in self.profiles.get(profile['id'],{}).items() if value is None or value in allowed}

    def get_units(self,profile):return dict(self.units.get(profile['id'],{}))

    def save(self,profile,mapping,source_units=None,replace_profile=False):
        from app_support import atomic_output
        from app_engineering_units import UNITS,unit
        allowed={c['id'] for c in profile['channels']}
        if any(v is not None and v not in allowed for v in mapping.values()):raise ValueError('Template canonical parameter is not in the profile')
        if source_units is not None and (not isinstance(source_units,dict) or any(not isinstance(value,str) or unit(value) not in UNITS for value in source_units.values())):raise ValueError('Invalid confirmed source units')
        record={**self.profiles,profile['id']:{**({} if replace_profile else self.get(profile)),**mapping}}
        units={**self.units,profile['id']:{**({} if replace_profile else self.get_units(profile)),**(source_units or {})}}
        with atomic_output(self.path) as temp:Path(temp).write_text(json.dumps({'version':1,'profiles':record,'source_units':units},indent=2),encoding='utf-8')
        self.profiles=record;self.units=units
