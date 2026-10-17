"""Lossless adapters for the application's historical preset/workspace schemas.

Unknown fields are retained. Unknown future schemas fail before mutating data;
XML entities and code/eval-based INI values are never executed.
"""
import configparser
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def scalar(text):
    if isinstance(text,str) and text.strip().lower() in ('true','false','none','null'):
        return {'true':True,'false':False,'none':None,'null':None}[text.strip().lower()]
    try:return json.loads(text)
    except (ValueError,TypeError):return text


def read_configuration(path):
    path=Path(path);text=path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() not in ('.xml','.ini','.cfg'):return migrate_configuration(json.loads(text))
    if len(text)>16*1024*1024:raise ValueError('Configuration is too large')
    if path.suffix.lower()=='.xml':
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('XML entities are not supported')
        root=ET.fromstring(text)
        payload=root.find('json')
        if payload is not None:record=json.loads(payload.text or '{}')
        else:
            def element(node):
                value={k:scalar(v) for k,v in node.attrib.items()}
                for child in node:
                    key=child.attrib.get('key') or child.attrib.get('name') or child.tag
                    item=element(child) if len(child) or child.attrib else scalar(child.text or '')
                    if isinstance(item,dict):item={k:v for k,v in item.items() if k not in ('key',)}
                    if key in value:raise ValueError('Duplicate XML configuration key: '+key)
                    value[key]=item
                return value if value else scalar(node.text or '')
            record=element(root)
    else:
        parser=configparser.ConfigParser(interpolation=None);parser.optionxform=str;parser.read_string(text)
        if parser.has_option('workspace','payload'):record=json.loads(parser.get('workspace','payload'))
        else:
            record={'version':3,'signals':{},'options':{}}
            for section in parser.sections():
                values={k:scalar(v) for k,v in parser.items(section)}
                if section.lower() in ('options','settings'):record['options'].update(values)
                elif section.startswith(('channel:','signal:')):record['signals'][section.split(':',1)[1]]=values
                else:record.setdefault('legacy_sections',{})[section]=values
    return migrate_configuration(record)


def migrate_configuration(record):
    if not isinstance(record,dict):raise ValueError('Configuration must contain an object')
    record=dict(record)
    # Known legacy wrappers and field names; preserve extra metadata verbatim.
    for wrapper in ('workspace','preset'):
        if isinstance(record.get(wrapper),dict):
            inner=dict(record[wrapper]);inner.setdefault('legacy_wrapper',{k:v for k,v in record.items() if k!=wrapper});record=inner;break
    if 'arrays' in record and 'channels' in record:
        if record.get('version',1)!=1:raise ValueError('Unsupported workspace version')
        record.setdefault('version',1);record.setdefault('views',record.get('layouts',[]));record.setdefault('ui',record.get('settings',{}))
        return record
    # Copy only small presets; duplicating millions of workspace cells would
    # unnecessarily double the memory cost of restoring a recording.
    record=deepcopy(record)
    if 'signals' not in record and isinstance(record.get('channel_configs'),dict):record['signals']=record['channel_configs']
    if 'signals' in record:
        if record.get('version',3) not in (1,2,3):raise ValueError('Unsupported preset version')
        record.setdefault('options',record.get('settings',{}));record['version']=max(3,record.get('version',3))
    return record
