"""Typed, provenance-preserving access to graph physical properties."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import cmath,math,statistics

EPS0=8.8541878128e-12; MU0=1.25663706212e-6; ETA0=math.sqrt(MU0/EPS0)
UNITS={'permittivity':'1','conductivity':'S m^-1','attenuation':'dB m^-1','frequency':'GHz','reflectance':'1','albedo':'1','heat_capacity':'J kg^-1 K^-1','density':'kg m^-3','thermal_conductivity':'W m^-1 K^-1','emissivity':'1'}
RANGES={'permittivity':(0,1e6,False),'conductivity':(0,1e9,True),'reflectance':(0,1,True),'albedo':(0,1,True),'heat_capacity':(0,1e5,False),'density':(0,1e5,False),'thermal_conductivity':(0,1e4,False),'emissivity':(0,1,True)}

@dataclass(frozen=True)
class PropertyRecord:
 scene:str; node_id:str; osm_id:str|None; surface:str|None; material_class:str|None
 property:str; state:str; value:float|None; unit:str|None; source:str|None; provenance:str|None
 derived:bool=False; formula:str|None=None; assumptions:tuple=()
 def dict(self): d=asdict(self);d['assumptions']=list(d['assumptions']);return d

def numeric(v):
 if v is None or isinstance(v,bool):return None
 try:x=float(v)
 except (TypeError,ValueError):return None
 return x if math.isfinite(x) else None
def property_key(prop,state='static'):
 if prop=='frequency':return 'frequency_ghz'
 return prop if state=='static' else f'{prop}_{state}'
def provenance(node,prop):
 source=node.get(f'{prop}_src')
 if prop in ('permittivity','conductivity'): source=node.get(f'{prop}_src') or node.get('permittivity_src' if prop=='permittivity' else 'conductivity_src')
 if prop in ('heat_capacity','density','thermal_conductivity','emissivity'):source=node.get('thermal_src')
 if prop in ('reflectance','albedo'):source=node.get('reflectance_src') or node.get('permittivity_src')
 cat='stored_source' if source=='metadata' else 'standard_derived' if source and 'ITU' in str(source) else 'literature_derived' if source else 'unspecified'
 return source,cat
def record(scene,nid,node,prop,state='static'):
 val=numeric(node.get(property_key(prop,state)));src,prov=provenance(node,prop)
 return PropertyRecord(scene,str(nid),node.get('osm_id'),node.get('surface'),node.get('material_class'),prop,state,val,UNITS.get(prop),src,prov)
def validate_value(prop,value):
 if value is None:return 'missing','No numeric value stored.'
 if prop not in RANGES:return 'unchecked','No controlled plausible range defined.'
 lo,hi,inclusive=RANGES[prop];ok=(lo<=value<=hi) if inclusive else (lo<value<=hi)
 return ('valid','Within controlled plausible range.') if ok else ('suspicious',f'Outside controlled range {lo}..{hi} {UNITS.get(prop)}.')
def pair(scene,nid,node,prop):return record(scene,nid,node,prop,'dry'),record(scene,nid,node,prop,'wet')
def em_state(epsilon_r,sigma,frequency_ghz):
 er=numeric(epsilon_r);sig=numeric(sigma);f=numeric(frequency_ghz)
 if f is None or f<=0:raise ValueError('frequency must be positive')
 if er is None or er<=0:raise ValueError('relative permittivity must be positive')
 if sig is None or sig<0:raise ValueError('conductivity must be nonnegative')
 omega=2*math.pi*f*1e9; eps=EPS0*er; ratio=sig/(omega*eps); root=math.sqrt(1+ratio*ratio); common=omega*math.sqrt(MU0*eps/2)
 alpha=common*math.sqrt(max(0,root-1));beta=common*math.sqrt(root+1)
 eta=cmath.sqrt(1j*omega*MU0/(sig+1j*omega*eps));gamma=(eta-ETA0)/(eta+ETA0)
 out={'epsilon_r_complex_real':er,'epsilon_r_complex_imag':-sig/(omega*EPS0),'loss_tangent':ratio,'alpha_np_per_m':alpha,'beta_rad_per_m':beta,'attenuation_db_per_m':8.686*alpha,'intrinsic_impedance_real_ohm':eta.real,'intrinsic_impedance_imag_ohm':eta.imag,'reflection_power':abs(gamma)**2}
 if not all(math.isfinite(v) for v in out.values()):raise ValueError('non-finite EM output')
 return out
def median(values):
 v=sorted(x for x in values if x is not None);return statistics.median(v) if v else None

def classify_application_property(node,prop):
 if (node.get('material_class') or '').lower()=='unknown':return 'unresolved'
 value=numeric(node.get(prop));
 if value is None:return 'missing'
 src,_=provenance(node,prop.split('_dry')[0].split('_wet')[0])
 reason=str(node.get('confidence_reason') or '').lower()
 if src=='metadata':return 'explicit_metadata'
 if src and ('ITU' in str(src) or 'standard' in str(src).lower()):return 'standard_derived'
 if 'class-level' in reason or src in (None,'default'):return 'generic_fallback'
 return 'computed' if 'computed' in str(src).lower() else 'standard_derived'
def radio_eligible(node,state):
 if (node.get('material_class') or '').lower()=='unknown' or not node.get('source_mesh_name',node.get('name')):return False
 return all(classify_application_property(node,f'{p}_{state}') in ('explicit_metadata','standard_derived','computed') for p in ('permittivity','conductivity'))
def reflectance_eligible(node):
 return (node.get('material_class') or '').lower()!='unknown' and bool(node.get('source_mesh_name',node.get('name'))) and classify_application_property(node,'reflectance')=='explicit_metadata'
def normalise(values,value):
 vals=[numeric(v) for v in values];vals=[v for v in vals if v is not None]
 if not vals:return None,None,None
 lo,hi=min(vals),max(vals);return (0.5 if hi==lo else (value-lo)/(hi-lo)),lo,hi
