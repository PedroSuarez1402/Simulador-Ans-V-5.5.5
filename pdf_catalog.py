import io, json, re
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

DATA_DIR = Path(__file__).resolve().parent / 'data'
RADIOS_FILE = DATA_DIR / 'radios.json'
ANTENNAS_FILE = DATA_DIR / 'antennas.json'


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path, default):
    ensure_data_dir()
    # Integración con capa de persistencia SQL (Fase 1)
    if path == RADIOS_FILE:
        try:
            from database.repositories import RadioRepository
            radios = RadioRepository.get_all()
            if radios:
                return radios
        except Exception:
            pass
    elif path == ANTENNAS_FILE:
        try:
            from database.repositories import AntennaRepository
            antennas = AntennaRepository.get_all()
            if antennas:
                return antennas
        except Exception:
            pass

    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding='utf-8')
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    ensure_data_dir()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    # Sincronizar automáticamente con SQL
    if path == RADIOS_FILE:
        try:
            from database.repositories import RadioRepository
            for r in data:
                RadioRepository.save(r)
        except Exception:
            pass
    elif path == ANTENNAS_FILE:
        try:
            from database.repositories import AntennaRepository
            for a in data:
                AntennaRepository.save(a)
        except Exception:
            pass


def extract_pdf_text(file_bytes):
    if PdfReader is None:
        raise RuntimeError('Falta la librería pypdf. Ejecuta el instalador de requirements.txt.')
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or '')
        except Exception:
            pages.append('')
    return '\n'.join(pages)


def _num(s):
    try:
        return float(str(s).replace(',', '.'))
    except Exception:
        return None


def _first(patterns, text, flags=re.I | re.S):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip()
    return None


def parse_range(text, labels):
    label = '(?:' + '|'.join(labels) + ')'
    m = re.search(label + r'.{0,250}?([0-9]+(?:\.[0-9]+)?)\s*[–\-]\s*([0-9]+(?:\.[0-9]+)?)\s*(GHz|MHz)', text, re.I | re.S)
    if not m:
        return None, None, None
    a, b, unit = _num(m.group(1)), _num(m.group(2)), m.group(3).lower()
    if unit == 'mhz':
        a, b = a / 1000, b / 1000
    return a, b, unit


def parse_radio_pdf(file_bytes, filename='datasheet.pdf'):
    text = extract_pdf_text(file_bytes)
    compact = re.sub(r'\s+', ' ', text)
    manufacturer = _first([r'\b(Mimosa Networks|Mimosa|Cambium Networks|Cambium|Ubiquiti|MikroTik|Radwin|Ceragon|Huawei)\b'], compact) or ''
    model = _first([
        r'(?:Datasheet\s*\|\s*)([A-Za-z0-9][A-Za-z0-9 _\-/\.]{1,40})',
        r'\b(C6x\s*Lite\s*Edition|C6x-LE|C6x|B6x)\b',
        r'\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z0-9][A-Za-z0-9\-]+){0,3})\s+\|\s+(?:High|Flexible|Essential)',
    ], compact) or Path(filename).stem
    fmin, fmax, _ = parse_range(compact, ['Frequency Range', 'Frequency'])
    power_s = _first([r'(?:Max Output Power|Maximum Output Power|TX Power)[^0-9\-]{0,30}(-?\d+(?:\.\d+)?)\s*dBm'], compact)
    gain_s = _first([r'(?:Integrated\s+)(\d+(?:\.\d+)?)\s*dBi\s+antenna', r'(?:antenna\s+gain)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*dBi'], compact)
    throughput_s = _first([r'(?:PTP:|PTP\s*)(\d+(?:\.\d+)?)\s*Gbps', r'(?:up to\s*)(\d+(?:\.\d+)?)\s*Gbps'], compact)
    bw = re.findall(r'(\d+)\s*MHz\s*(?:channels?)?', compact, re.I)
    bandwidths = sorted({int(x) for x in bw if int(x) <= 320})
    mimo = _first([r'(\d+x\d+)\s*(?:MU-)?MIMO', r'MIMO[^\d]*(\d+x\d+)'], compact) or ''
    modulation = _first([r'MIMO\s*&\s*Modulation\s*([^\n]{0,120})', r'Modulation\s*[: ]*([^\n]{0,100})'], text) or ''
    rx = {}
    for m in re.finditer(r'(-\d+(?:\.\d+)?)\s*dBm\s*(?:@|at)\s*(\d+)\s*MHz', compact, re.I):
        rx[int(m.group(2))] = float(m.group(1))
    return {
        'manufacturer': manufacturer or 'Desconocido', 'model': model.strip(), 'source_file': filename,
        'frequency_min_ghz': fmin, 'frequency_max_ghz': fmax, 'max_output_power_dbm': _num(power_s),
        'integrated_antenna_gain_dbi': _num(gain_s), 'throughput_gbps': _num(throughput_s),
        'bandwidths_mhz': bandwidths, 'mimo': mimo, 'modulation': modulation.strip(),
        'rx_sensitivity_dbm': rx, 'notes': 'Datos extraídos automáticamente del datasheet; revisar antes de usar en diseño definitivo.'
    }, text


def parse_antenna_pdf(file_bytes, filename='antenna.pdf'):
    """Extract one or many antenna variants from a datasheet.

    The parser is intentionally conservative. It has a specific parser for the
    ALGcom UHP-5800 Full Band sheet because that sheet contains four models in
    one table, and then falls back to generic regexes for other manufacturers.
    """
    text = extract_pdf_text(file_bytes)
    compact = re.sub(r'\s+', ' ', text)
    manufacturer = _first([
        r'\b(ALGcom|Mimosa Networks|Mimosa|Cambium Networks|Cambium|Ubiquiti|MikroTik|Radwin|Ceragon|Huawei)\b'
    ], compact) or ''
    products = []

    # ALGcom UHP-5800 Full Band: four variants share the same frequency range.
    # Values are read from the electrical/mechanical table rather than inferred
    # from graphics, so they remain editable by the user after detection.
    if 'UHP-5800-25-03-DP' in compact and 'UHP-5800-35-12-DP' in compact:
        variants = [
            ('UHP-5800-25-03-DP', 0.30, 26.8, 26.2, 23.0, 8.8, '>40 dB', 3.2, 0.138, '+/- 7.5°', '', 'N fêmea / SMA Fêmea Reverso'),
            ('UHP-5800-30-06-DP', 0.60, 30.5, 29.5, 28.5, 5.8, '>50 dB', 6.0, 0.393, '+/- 7.5°', '', 'N fêmea / SMA Fêmea Reverso'),
            ('UHP-5800-32-09-DP', 0.90, 33.2, 32.5, 30.0, 3.1, '>55 dB', 15.5, 0.698, '+/- 15°', '+/- 18°', 'N fêmea / SMA Fêmea Reverso / Mimosa C5x'),
            ('UHP-5800-35-12-DP', 1.20, 36.0, 34.8, 33.1, 2.4, '>57 dB', 25.0, 1.393, '+/- 10°', '+/- 25°', 'N fêmea / SMA Fêmea Reverso / Mimosa C5x'),
        ]
        for model, diameter, high, mid, low, beam, ftb, weight, wind_area, elev, azim, connector in variants:
            products.append({
                'manufacturer': 'ALGcom', 'model': model, 'source_file': filename,
                'frequency_min_ghz': 4.9, 'frequency_max_ghz': 6.425,
                'diameter_m': diameter, 'gain_dbi': high,
                'gain_low_dbi': low, 'gain_mid_dbi': mid, 'gain_high_dbi': high,
                'beamwidth_deg': beam, 'polarization': 'Doble (V y H o +/-45°)',
                'shielding': 'Sí — reflector Deep Dish', 'front_to_back_ratio_db': ftb,
                'xpd_db': '>27 dB' if diameter == 0.30 else '>30 dB',
                'vswr': '1.8:1 max / 1.6:1 typ', 'port_isolation_db': '>30 dB',
                'connector': connector, 'elevation_adjustment': elev,
                'azimuth_adjustment': azim, 'polarization_adjustment': '+/- 5°',
                'weight_kg': weight, 'mast_mount': 'Ø1”-Ø2”' if diameter <= 0.60 else ('Ø2”-Ø4.1/2”' if diameter == 0.90 else 'Ø3”-Ø4.1/2”'),
                'operational_wind_kmh': 110, 'survival_wind_kmh': 200,
                'wind_area_m2': wind_area, 'material': 'Metal / reflector Deep Dish',
                'notes': 'Detectado automáticamente del datasheet ALGcom. Revisar antes de diseño definitivo.'
            })
        return products, text

    # Mimosa N5-X family: explicit names avoid column-order mistakes.
    explicit = [('N5-X12',12,38.0),('N5-X16',16,22.0),('N5-X20',20,12.0),('N5-X25',25,8.0),('N5-X30kp',30,5.75)]
    if 'N5-X12' in compact or 'N5-X30kp' in compact:
        products = [{
            'manufacturer':'Mimosa','model':m,'gain_dbi':float(g),'beamwidth_deg':b,
            'polarization':'Dual-slant 45°','source_file':filename,
            'frequency_min_ghz':5.15,'frequency_max_ghz':7.125,
            'shielding':'No especificado','notes':'Detectado automáticamente del datasheet; revisar.'
        } for m,g,b in explicit if m in compact]
    else:
        known = re.findall(r'\b([A-Z][A-Za-z0-9\-]+)\b[^\n]{0,100}?(\d{1,2})\s*dBi[^\n]{0,80}?([0-9]+(?:\.[0-9]+)?)°', text, re.I)
        for prod, gain, beam in known:
            products.append({
                'manufacturer': manufacturer or 'Desconocido', 'model': prod,
                'gain_dbi': float(gain), 'beamwidth_deg': float(beam),
                'polarization': '', 'source_file': filename,
                'notes': 'Detectado automáticamente; revisar campos manualmente.'
            })
    return products, text
