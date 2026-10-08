import json
import re
import zipfile
from io import BytesIO
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

VERSION = 'V5.5.5'
DEFAULT_PROJECTS_DIR = Path(__file__).resolve().parent / 'data' / 'projects'
SETTINGS_FILE = Path(__file__).resolve().parent / 'data' / 'app_settings.json'


def get_projects_dir():
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            p = data.get('projects_dir')
            if p:
                path = Path(p).expanduser()
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    return path
                except Exception:
                    pass
    except Exception:
        pass
    return DEFAULT_PROJECTS_DIR


def set_projects_dir(path):
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps({'projects_dir': str(p)}, ensure_ascii=False, indent=2), encoding='utf-8')
    return p

# Backward-compatible name; application code should use get_projects_dir().
PROJECTS_DIR = DEFAULT_PROJECTS_DIR

def jsonable(obj):
    """Convert application state to strict JSON-safe Python values.
    NaN/Infinity (common in pandas/NumPy tables) become None so JSON
    serialization with allow_nan=False never fails.
    """
    if obj is None:
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        return value if np.isfinite(value) else None
    if isinstance(obj, (float,)):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, (np.ndarray,)):
        return [jsonable(x) for x in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return [jsonable(x) for x in obj.to_dict(orient='records')]
    if isinstance(obj, pd.Series):
        return [jsonable(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(x) for x in obj]
    # pandas missing scalar (pd.NA / NaT) and other NA-like values
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    # Datetime-like objects are stored as strings.
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj

def ensure_projects_dir():
    get_projects_dir().mkdir(parents=True, exist_ok=True)

def safe_filename(name):
    safe = re.sub(r'[^A-Za-z0-9ÁÉÍÓÚáéíóúÑñ _.-]+', '', str(name)).strip().replace(' ', '_')
    return (safe[:100] or 'proyecto') + '.slp.json'

def list_projects():
    ensure_projects_dir(); rows=[]
    for p in sorted(get_projects_dir().glob('*.slp.json'), key=lambda x:x.stat().st_mtime, reverse=True):
        try:
            d=json.loads(p.read_text(encoding='utf-8')); m=d.get('meta',{}); c=d.get('link_config',{})
            rows.append({'name':m.get('name',p.stem), 'file':p.name, 'modified':m.get('modified',''), 'site_a':c.get('name_a',''), 'site_b':c.get('name_b','')})
        except Exception: pass
    return rows

def save_project(name, state):
    ensure_projects_dir(); now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    payload={'format':'SAF-Link-Planner-Project','version':VERSION,'meta':{'name':name,'modified':now}, **jsonable(state)}
    path=get_projects_dir()/safe_filename(name)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path,payload

def load_project(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def df_from(records, columns=None):
    if records is None: return None
    df=pd.DataFrame(records)
    if columns:
        for c in columns:
            if c not in df.columns: df[c]=np.nan
        df=df[columns]
        # Streamlit CheckboxColumn requires a real boolean dtype. Older/saved
        # projects can contain nulls in `activo`, which pandas loads as FLOAT
        # (e.g. 1.0/NaN). Normalize every activity flag after loading.
        for c in [c for c in columns if c == 'activo']:
            def _to_bool(v):
                if pd.isna(v):
                    return False
                if isinstance(v, str):
                    return v.strip().lower() in ('true','1','si','sí','yes','y','on')
                return bool(v)
            df[c] = df[c].map(_to_bool).astype(bool)
    return df

def create_kmz(kml_bytes):
    bio=BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z: z.writestr('doc.kml',kml_bytes)
    return bio.getvalue()

def rich_kml(df, cfg, radio_a, radio_b, ant_a, ant_b, critical, manual, rf):
    '''Exporta un KMZ visualmente cercano al concepto de LINKPlanner.

    Diseño deliberadamente simple y robusto para Google Earth:
    - LOS magenta con cotas absolutas reales.
    - Fresnel 60% como una sucesión de paneles, no como un único polígono gigante.
      Esto evita que Google Earth descarte o deforme la geometría.
    - Proyección Fresnel sobre el terreno.
    - Cortina Fresnel vertical azul translúcida.
    - Solo hasta 3 advertencias de obstrucciones relevantes.
    - Sin pines individuales para cada árbol.
    '''
    def esc(v):
        return str(v if v is not None else '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

    def f(v, default=0.0):
        try:
            x=float(v)
            return x if np.isfinite(x) else default
        except Exception:
            return default

    def coords(points):
        return ' '.join(f'{x:.7f},{y:.7f},{z:.2f}' for x,y,z in points)

    # ---------------- Perfil ----------------
    dfw = None
    if df is not None and not df.empty:
        dfw=df.copy()
        for c in ['distance_km','lat','lon','elevation_m']:
            if c not in dfw.columns: dfw[c]=np.nan
            dfw[c]=pd.to_numeric(dfw[c],errors='coerce')
        dfw=dfw.dropna(subset=['distance_km','lat','lon','elevation_m']).sort_values('distance_km').reset_index(drop=True)

    terrain_a=terrain_b=0.0
    top_a=f(cfg.get('height_a')); top_b=f(cfg.get('height_b'))
    dist_km=0.0
    los=[]; rad=[]; rows=[]

    if dfw is not None and len(dfw)>=2:
        rows=list(dfw.itertuples(index=False))
        dist_km=f(dfw.distance_km.iloc[-1])
        terrain_a=f(dfw.elevation_m.iloc[0]); terrain_b=f(dfw.elevation_m.iloc[-1])
        top_a=terrain_a+f(cfg.get('height_a')); top_b=terrain_b+f(cfg.get('height_b'))
        if 'los_worst_m' in dfw.columns:
            los=pd.to_numeric(dfw.los_worst_m,errors='coerce').to_numpy(float)
        elif 'los_m' in dfw.columns:
            los=pd.to_numeric(dfw.los_m,errors='coerce').to_numpy(float)
        else:
            los=np.linspace(top_a,top_b,len(dfw))
        fallback=np.linspace(top_a,top_b,len(dfw))
        los=np.where(np.isfinite(los),los,fallback)
        if 'fresnel_60_m' in dfw.columns:
            rad=pd.to_numeric(dfw.fresnel_60_m,errors='coerce').fillna(0).to_numpy(float)
        elif 'f1_radius_m' in dfw.columns:
            rad=0.60*pd.to_numeric(dfw.f1_radius_m,errors='coerce').fillna(0).to_numpy(float)
        else:
            rad=np.zeros(len(dfw))
        rad=np.maximum(np.where(np.isfinite(rad),rad,0),0)

    # ---------------- Geometría local ----------------
    ground_left=[]; ground_right=[]
    upper_left=[]; upper_right=[]; lower_left=[]; lower_right=[]
    terrain_line=[]; los_line=[]
    if rows:
        lat0=f(cfg.get('lat_a')); lon0=f(cfg.get('lon_a'))
        coslat=max(0.1,np.cos(np.radians(lat0)))
        xm=(dfw.lon.to_numpy(float)-lon0)*111320.0*coslat
        ym=(dfw.lat.to_numpy(float)-lat0)*110540.0
        dx=xm[-1]-xm[0]; dy=ym[-1]-ym[0]
        norm=max(1e-9,float(np.hypot(dx,dy)))
        px,py=-dy/norm,dx/norm
        for i,r in enumerate(rows):
            terrain_line.append((f(r.lon),f(r.lat),f(r.elevation_m)))
            los_line.append((f(r.lon),f(r.lat),f(los[i])))
            w=f(rad[i])
            lx=xm[i]+px*w; ly=ym[i]+py*w
            rx=xm[i]-px*w; ry=ym[i]-py*w
            llon=lon0+lx/(111320.0*coslat); llat=lat0+ly/110540.0
            rlon=lon0+rx/(111320.0*coslat); rlat=lat0+ry/110540.0
            ground_left.append((llon,llat,f(r.elevation_m)+0.5))
            ground_right.append((rlon,rlat,f(r.elevation_m)+0.5))
            upper_left.append((llon,llat,f(los[i]+w)))
            upper_right.append((rlon,rlat,f(los[i]+w)))
            lower_left.append((llon,llat,f(los[i]-w)))
            lower_right.append((rlon,rlat,f(los[i]-w)))

    # ---------------- Descripciones ----------------
    def rdesc(r):
        return '<br/>'.join([
            f"Fabricante: {esc(r.get('manufacturer',''))}",
            f"Modelo: {esc(r.get('model',''))}",
            f"Frecuencia: {f(r.get('frequency_min_ghz'),float('nan')):.2f}–{f(r.get('frequency_max_ghz'),float('nan')):.2f} GHz",
            f"Potencia TX máx.: {f(r.get('max_output_power_dbm'),float('nan')):.1f} dBm",
            f"MIMO: {esc(r.get('mimo',''))}",
            f"Modulación: {esc(r.get('modulation',''))}",
        ])
    def adesc(a):
        return '<br/>'.join([
            f"Fabricante: {esc(a.get('manufacturer',''))}",
            f"Modelo: {esc(a.get('model',''))}",
            f"Tipo: {esc(a.get('antenna_type',a.get('type','Direccional')))}",
            f"Ganancia: {f(a.get('gain_dbi'),float('nan')):.1f} dBi",
            f"Beamwidth: {f(a.get('beamwidth_deg'),float('nan')):.1f}°",
        ])

    styles='''
<Style id="los"><LineStyle><color>ffff00ff</color><width>5</width></LineStyle></Style>
<Style id="fEdge"><LineStyle><color>ffff00ff</color><width>2</width></LineStyle></Style>
<Style id="fGround"><LineStyle><color>66ff00ff</color><width>1</width></LineStyle><PolyStyle><color>38ff00ff</color><fill>1</fill><outline>1</outline></PolyStyle></Style>
<Style id="fVertical"><LineStyle><color>660000ff</color><width>1</width></LineStyle><PolyStyle><color>300000ff</color><fill>1</fill><outline>1</outline></PolyStyle></Style>
<Style id="terrain"><LineStyle><color>cc663300</color><width>2</width></LineStyle></Style>
<Style id="site"><IconStyle><scale>1.15</scale></IconStyle><LabelStyle><scale>1.0</scale></LabelStyle></Style>
<Style id="warn"><IconStyle><scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href></Icon></IconStyle><LabelStyle><scale>0.9</scale></LabelStyle></Style>
<Style id="manual"><LineStyle><color>aa0000ff</color><width>2</width></LineStyle><PolyStyle><color>350000ff</color><fill>1</fill><outline>1</outline></PolyStyle></Style>
'''

    folders=[]
    # 01 enlace
    folders.append(f'''<Folder><name>01 - Enlace</name><open>1</open>
<Placemark><name>LOS — {esc(cfg.get('name_a','A'))} → {esc(cfg.get('name_b','B'))}</name><styleUrl>#los</styleUrl>
<description><![CDATA[<b>Distancia:</b> {dist_km:.3f} km<br/><b>Cota antena A:</b> {top_a:.2f} m<br/><b>Cota antena B:</b> {top_b:.2f} m<br/><b>Altura A:</b> {f(cfg.get('height_a')):.2f} m<br/><b>Altura B:</b> {f(cfg.get('height_b')):.2f} m<br/><b>Radio A:</b> {esc(radio_a.get('model',''))}<br/><b>Radio B:</b> {esc(radio_b.get('model',''))}<br/><b>Antena A:</b> {esc(ant_a.get('model',''))}<br/><b>Antena B:</b> {esc(ant_b.get('model',''))}]]></description>
<LineString><altitudeMode>absolute</altitudeMode><tessellate>1</tessellate><coordinates>{coords(los_line)}</coordinates></LineString></Placemark></Folder>''')

    # 02 sitios
    folders.append(f'''<Folder><name>02 - Sitios y alturas</name><open>1</open>
<Placemark><name>A — {esc(radio_a.get('model',''))} / {esc(ant_a.get('model',''))}</name><styleUrl>#site</styleUrl><description><![CDATA[{rdesc(radio_a)}<br/><br/>{adesc(ant_a)}<br/><b>Cota:</b> {top_a:.2f} m]]></description><Point><altitudeMode>absolute</altitudeMode><coordinates>{f(cfg.get('lon_a')):.7f},{f(cfg.get('lat_a')):.7f},{top_a:.2f}</coordinates></Point></Placemark>
<Placemark><name>B — {esc(radio_b.get('model',''))} / {esc(ant_b.get('model',''))}</name><styleUrl>#site</styleUrl><description><![CDATA[{rdesc(radio_b)}<br/><br/>{adesc(ant_b)}<br/><b>Cota:</b> {top_b:.2f} m]]></description><Point><altitudeMode>absolute</altitudeMode><coordinates>{f(cfg.get('lon_b')):.7f},{f(cfg.get('lat_b')):.7f},{top_b:.2f}</coordinates></Point></Placemark>
<Placemark><name>Altura A sobre terreno</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{f(cfg.get('lon_a')):.7f},{f(cfg.get('lat_a')):.7f},{terrain_a:.2f} {f(cfg.get('lon_a')):.7f},{f(cfg.get('lat_a')):.7f},{top_a:.2f}</coordinates></LineString></Placemark>
<Placemark><name>Altura B sobre terreno</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{f(cfg.get('lon_b')):.7f},{f(cfg.get('lat_b')):.7f},{terrain_b:.2f} {f(cfg.get('lon_b')):.7f},{f(cfg.get('lat_b')):.7f},{top_b:.2f}</coordinates></LineString></Placemark></Folder>''')

    # 03 Fresnel sobre terreno: muchos paneles pequeños, robustos en Google Earth.
    if len(ground_left)>=2:
        parts=[]
        for i in range(len(ground_left)-1):
            poly=coords([ground_left[i],ground_left[i+1],ground_right[i+1],ground_right[i],ground_left[i]])
            parts.append(f'<Placemark><name>Fresnel terreno {i+1}</name><styleUrl>#fGround</styleUrl><Polygon><altitudeMode>absolute</altitudeMode><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{poly}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
        parts.append(f'<Placemark><name>Borde Fresnel izquierdo</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(ground_left)}</coordinates></LineString></Placemark>')
        parts.append(f'<Placemark><name>Borde Fresnel derecho</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(ground_right)}</coordinates></LineString></Placemark>')
        folders.append(f'<Folder><name>03 - Fresnel 60% sobre terreno</name><open>1</open>{"".join(parts)}</Folder>')

    # 04 Fresnel vertical: paneles entre cada par de puntos, usando alturas absolutas.
    if len(upper_left)>=2:
        parts=[]
        for i in range(len(upper_left)-1):
            poly=coords([upper_left[i],upper_left[i+1],lower_left[i+1],lower_left[i],upper_left[i]])
            parts.append(f'<Placemark><name>Fresnel vertical L {i+1}</name><styleUrl>#fVertical</styleUrl><Polygon><altitudeMode>absolute</altitudeMode><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{poly}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
            poly2=coords([upper_right[i],upper_right[i+1],lower_right[i+1],lower_right[i],upper_right[i]])
            parts.append(f'<Placemark><name>Fresnel vertical R {i+1}</name><styleUrl>#fVertical</styleUrl><Polygon><altitudeMode>absolute</altitudeMode><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{poly2}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
        parts += [
            f'<Placemark><name>Borde superior Fresnel</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(upper_left)}</coordinates></LineString></Placemark>',
            f'<Placemark><name>Borde inferior Fresnel</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(lower_left)}</coordinates></LineString></Placemark>',
            f'<Placemark><name>Borde superior Fresnel derecho</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(upper_right)}</coordinates></LineString></Placemark>',
            f'<Placemark><name>Borde inferior Fresnel derecho</name><styleUrl>#fEdge</styleUrl><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coords(lower_right)}</coordinates></LineString></Placemark>',
        ]
        folders.append(f'<Folder><name>04 - Fresnel 60% vertical</name><open>1</open>{"".join(parts)}</Folder>')

    if terrain_line:
        folders.append(f'<Folder><name>05 - Perfil terreno 3D</name><open>0</open><Placemark><name>Terreno con elevación real</name><styleUrl>#terrain</styleUrl><LineString><altitudeMode>absolute</altitudeMode><tessellate>1</tessellate><coordinates>{coords(terrain_line)}</coordinates></LineString></Placemark></Folder>')

    # 06 advertencias: máximo 3, separadas geográficamente.
    warnings=[]
    if critical is not None and not critical.empty:
        c=critical.copy()
        for col in ['distance_km','lat','lon','los_clearance_m','fresnel_clearance_m','canopy_top_m','canopy_height_m']:
            if col in c.columns: c[col]=pd.to_numeric(c[col],errors='coerce')
        if 'los_clearance_m' in c.columns and 'fresnel_clearance_m' in c.columns:
            c=c[(c.los_clearance_m<0)|(c.fresnel_clearance_m<0)].copy()
            if not c.empty:
                c['sev']=np.minimum(c.los_clearance_m,c.fresnel_clearance_m)
                selected=[]
                for _,r in c.sort_values('sev').iterrows():
                    if all(abs(float(r.distance_km)-float(q.distance_km))>=0.20 for q in selected):
                        selected.append(r)
                    if len(selected)>=3: break
                for i,r in enumerate(selected,1):
                    losm=f(r.los_clearance_m); fm=f(r.fresnel_clearance_m); kind='OBSTRUCCIÓN LOS' if losm<0 else 'INTRUSIÓN FRESNEL 60%'
                    warnings.append(f'<Placemark><name>⚠ Hp{i} — {kind} — {f(r.distance_km):.3f} km</name><styleUrl>#warn</styleUrl><description><![CDATA[<b>{kind}</b><br/>Distancia desde A: {f(r.distance_km):.3f} km<br/>Altura obstáculo: {f(r.canopy_height_m):.1f} m<br/>Cota superior: {f(r.canopy_top_m):.1f} m<br/>Margen LOS: {losm:.1f} m<br/>Margen Fresnel 60%: {fm:.1f} m]]></description><Point><altitudeMode>absolute</altitudeMode><coordinates>{f(r.lon):.7f},{f(r.lat):.7f},{f(r.canopy_top_m):.2f}</coordinates></Point></Placemark>')
    if not warnings:
        warnings=['<Placemark><name>✓ Sin obstáculos críticos</name></Placemark>']
    folders.append(f'<Folder><name>06 - Advertencias principales (máx. 3)</name><open>1</open>{"".join(warnings)}</Folder>')

    # 07 manuales 3D
    def local_box(lat,lon,w,d,z):
        cl=max(0.1,np.cos(np.radians(lat)))
        return [(lon-w/(2*111320*cl),lat-d/(2*110540),z),(lon+w/(2*111320*cl),lat-d/(2*110540),z),(lon+w/(2*111320*cl),lat+d/(2*110540),z),(lon-w/(2*111320*cl),lat+d/(2*110540),z)]
    obs=[]
    if manual is not None and not manual.empty and dfw is not None and len(dfw)>=2:
        for row in manual.itertuples(index=False):
            if not bool(getattr(row,'activo',True)): continue
            d=f(getattr(row,'distancia_km',0)); h=max(0,f(getattr(row,'altura_m',0))); w=max(1,f(getattr(row,'ancho_m',4)))
            lat=float(np.interp(d,dfw.distance_km,dfw.lat)); lon=float(np.interp(d,dfw.distance_km,dfw.lon)); ground=float(np.interp(d,dfw.distance_km,dfw.elevation_m))
            base=local_box(lat,lon,w,max(2,w*0.5),ground); top=[(x,y,ground+h) for x,y,_ in base]
            faces=[]
            for i in range(4):
                faces.append(f'<Polygon><altitudeMode>absolute</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords([base[i],base[(i+1)%4],top[(i+1)%4],top[i],base[i]])}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
            faces.append(f'<Polygon><altitudeMode>absolute</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords(top+[top[0]])}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
            obs.append(f'<Placemark><name>{esc(getattr(row,"nombre","Obstáculo"))} — {esc(getattr(row,"tipo","Obstáculo"))}</name><styleUrl>#manual</styleUrl><description><![CDATA[Distancia: {d:.3f} km<br/>Altura: {h:.1f} m<br/>Cota superior: {ground+h:.1f} m]]></description><MultiGeometry>{"".join(faces)}</MultiGeometry></Placemark>')
    folders.append(f'<Folder><name>07 - Obstáculos manuales 3D</name><open>0</open>{"".join(obs) or "<Placemark><name>No hay obstáculos manuales activos</name></Placemark>"}</Folder>')

    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f'<name>SAF Link Planner — {esc(cfg.get("name_a","A"))} a {esc(cfg.get("name_b","B"))}</name>'
            + styles + ''.join(folders) + '</Document></kml>').encode('utf-8')
