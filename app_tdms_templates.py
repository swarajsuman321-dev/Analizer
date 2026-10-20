"""Exact source identities map to reviewed labels; templates never contain samples."""
from dataclasses import replace
import json
import re
from pathlib import Path
from PySide6 import QtCore,QtWidgets
from app_compact_forms import add_help
from app_output import output_path


def suggested_name(channel):
    name=channel.attributes.get('original_name',channel.name)
    known={
        'MCB_MotorControlBridge_sDataResourceTemperatureMeasurement_ucMotorTemperature_0_R':'Motor temperature',
        'PDH_AAS_UI_ACTUAL_SPEED_0_R':'Actual motor speed',
        'PDH_AAS_UI_MOTOR_IS_ERROR_0_R':'Motor error code',
        'PDH_AAS_UI_REFERENCE_SPEED_0_R':'Reference motor speed',
        'PDH_ASO_D_UC_PROG_SEL_POSITION_0_R':'Program selector position',
        'PDH_ERRH_UI_ERROR_DETECTION_FAILURE_MESSAGES_11_0_R':'Failure message 11',
        'PDH_FOA_B_FOAM_DETECTED_0_R':'Foam detected',
        'PDH_FSS_D_B_RINSE_HOLD_ACTIVE_0_R':'Rinse hold active',
        'PDH_INCT2_UI_CURRENT_STWF_NUMBER_0_R':'Current step number',
        'PDH_MOC_UI_TARGET_SPEED_0_R':'Target motor speed',
        'PDH_PUD_D_UC_PROGRESS_STATE_0_R':'Program progress state',
        'PDH_PUD_STM_D_B_LOW_WATER_PREASURE_DETECTED_0_R':'Low water pressure detected',
        'PDH_TMT2_UC_T_IST_0_R':'Water temperature',
        'PDH_UBC_UI_MEASURED_UNBALANCE_0_R':'Measured imbalance',
        'PDH_WLA2_UI_P_IST_0_R':'Water pressure',
        'PDH_WQMT2_UI_WATER_QUANTITY_0_R':'Water quantity',
        'dE2Prom_Offset_LastError_0_R':'Last stored error',
    }
    if name in known:return known[name]
    match=re.fullmatch(r'PDH_INT_AUC_DEVICE_STATE_1_VALUE_(\d+)_0_R',name)
    if match:return 'Device state '+match[1]
    # Known logger syntax: remove transport prefixes, retain unknown signal words.
    short=re.sub(r'^PDH_(?:AAS_B_|RTH_D_UI_)','',name,flags=re.I)
    short=re.sub(r'_\d+_R$','',short,flags=re.I)
    known={'HEATER_ON':'Heater','PU':'Pump','REMAIN_TIME_MINUTES':'Remaining time'}
    short=known.get(short,short)
    if re.fullmatch(r'V\d+',short):short='Valve '+short[1:]
    short=re.sub(r'[_\s]+',' ',short).strip()
    return short[:100] or name


def identity(channel):
    # Full TDMS group/channel identity prevents unrelated sensors sharing a label.
    return str(channel.attributes.get('tdms_template_key',channel.attributes.get('source_column',channel.name)))


class ParameterTemplates:
    def __init__(self,path=None):
        self.path=Path(path) if path else output_path('tdms-parameters.json','templates')
        self.entries={};self.warning=''
        if self.path.exists():
            try:
                record=json.loads(self.path.read_text(encoding='utf-8'))
                if record.get('version')!=1 or not isinstance(record.get('parameters'),dict):raise ValueError('Unsupported template format')
                self.entries=record['parameters']
                for value in self.entries.values():self.validate(value)
            except (OSError,ValueError,TypeError,AttributeError) as exc:
                self.entries={};self.warning=f'The saved template could not be read: {exc}. Review parameters again; the file is kept until you save a new review.'

    @staticmethod
    def validate(value):
        if not isinstance(value,dict) or not isinstance(value.get('name'),str) or not value['name'].strip():raise ValueError('Every parameter needs a display name')
        if not isinstance(value.get('unit'),str) or value.get('interpretation') not in ('auto','numeric','actuator'):raise ValueError('Invalid parameter settings')

    def unknown(self,store):
        return [c for c in store.channels.values() if c.attributes.get('format')=='TDMS' and identity(c) not in self.entries]

    def save(self,entries):
        for entry in entries.values():self.validate(entry)
        updated={**self.entries,**entries}
        from app_support import atomic_output
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with atomic_output(self.path) as temporary:
            Path(temporary).write_text(json.dumps({'version':1,'parameters':updated},ensure_ascii=False,indent=2),encoding='utf-8')
        self.entries=updated

    def apply(self,store):
        from app_actuators import interpret_channel
        for id,c in list(store.channels.items()):
            if c.attributes.get('format')!='TDMS':continue
            entry=self.entries.get(identity(c))
            if not entry:continue
            if c.attributes.get('comparison_source'):
                # Comparison values have already been converted to reference
                # units. Apply the reviewed label without relabelling those
                # numbers or reinterpreting derived traces a second time.
                store.channels[id]=replace(c,name=entry['name']+' · '+c.attributes['comparison_source'])
                continue
            original=c.attributes.get('original_name',c.name)
            attrs={**c.attributes,'original_name':original,'value_interpretation':entry['interpretation'],'template_key':identity(c),'template_display_name':entry['name']}
            # Unit is metadata, not a numerical conversion. Raw readings stay intact.
            attrs['raw_unit']=entry['unit']
            updated=replace(c,unit=entry['unit'],attributes=attrs)
            updated=interpret_channel(updated)
            store.channels[id]=replace(updated,name=entry['name'])


class ParameterReview(QtWidgets.QDialog):
    def __init__(self,channels,parent=None,warning=''):
        super().__init__(parent);self.setWindowTitle('Review TDMS parameters');self.resize(1000,650)
        self.channels=list({identity(c):c for c in channels}.values())
        layout=QtWidgets.QVBoxLayout(self)
        text='Review new parameters once. Edit short names and units; choose ON/OFF only for actual actuator commands. Raw measurements and original names are preserved. Known parameters use your saved template automatically.'
        # Optional guidance must not force the review table wider or taller.
        # Template failures remain visible because the user must act on them.
        self.help=add_help(layout,text)
        if warning:
            self.warning=QtWidgets.QLabel(warning);self.warning.setWordWrap(True)
            self.warning.setAccessibleName('Template warning');layout.addWidget(self.warning)
        self.table=QtWidgets.QTableWidget(len(self.channels),5);self.table.setHorizontalHeaderLabels(['Original parameter','Display name','Unit','Interpretation','Samples / range'])
        layout.addWidget(self.table)
        for row,c in enumerate(self.channels):
            source=QtWidgets.QTableWidgetItem(c.attributes.get('original_name',c.name));source.setToolTip(identity(c));source.setFlags(source.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable);self.table.setItem(row,0,source)
            self.table.setItem(row,1,QtWidgets.QTableWidgetItem(suggested_name(c)));self.table.setItem(row,2,QtWidgets.QTableWidgetItem(c.attributes.get('raw_unit',c.unit)))
            combo=QtWidgets.QComboBox()
            for label,value in [('Automatic','auto'),('Raw numeric','numeric'),('ON/OFF','actuator')]:combo.addItem(label,value)
            combo.setToolTip('ON/OFF: zero is OFF; finite nonzero integers are ON. Missing and fractional values stay unknown.')
            self.table.setCellWidget(row,3,combo)
            import numpy as np
            raw=c.raw_y if c.raw_y is not None else c.y;finite=raw[np.isfinite(raw)]
            summary=f'{len(raw):,} samples · '+(f'{finite.min():.5g} to {finite.max():.5g}' if len(finite) else 'No valid readings')
            item=QtWidgets.QTableWidgetItem(summary);item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable);self.table.setItem(row,4,item)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(0,280)
        self.error=QtWidgets.QLabel();self.error.setWordWrap(True)
        self.error.setAccessibleName('Parameter validation error');layout.addWidget(self.error)
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText('Save template and load');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def entries(self):
        result={}
        for row,c in enumerate(self.channels):
            value={'name':self.table.item(row,1).text().strip(),'unit':self.table.item(row,2).text().strip(),'interpretation':self.table.cellWidget(row,3).currentData()}
            ParameterTemplates.validate(value);result[identity(c)]=value
        return result

    def accept(self):
        try:self.entries()
        except ValueError as exc:self.error.setText(str(exc));return
        super().accept()


def engineering_columns(frame):
    """Resolve projected engineering names to the original TDMS value path.

    Raw column identity stays unchanged for alignment deduplication and export.
    Template v1 keys remain exactly compatible with files reviewed through Open.
    """
    result={}
    for key,spec in frame.attrs.get('tdms_projections',{}).items():
        name=spec['name'] if spec['group']=='Measurements' else spec['group']+' / '+spec['name']
        result[name]={'format':'TDMS','tdms_template_key':key,'original_name':spec['name'],
                      'tdms_group':spec['tdms_group']}
    return result
