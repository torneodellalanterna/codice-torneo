import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime, date

st.set_page_config(page_title="Torneo Calcio", layout="wide")

st.title("Torneo di Calcio — App gestionale (ITA)")
st.markdown("App semplice per gestire calendario, risultati, classifica, marcatori, cartellini, loghi e fase a eliminazione.")

# --- Helpers ---------------------------------------------------------------

def init_state():
    if 'teams' not in st.session_state:
        st.session_state['teams'] = ['' for _ in range(20)]
    if 'team_logos' not in st.session_state:
        st.session_state['team_logos'] = {t: None for t in st.session_state['teams']}
    if 'calendar' not in st.session_state:
        cols = ['Giornata', 'Data', 'Ora', 'Luogo', 'Squadra Casa', 'Gol Casa',
                'Squadra Trasferta', 'Gol Trasferta', 'Marcatori', 'Cartellini']
        st.session_state['calendar'] = pd.DataFrame(columns=cols)
    if 'knockout' not in st.session_state:
        st.session_state['knockout'] = pd.DataFrame(columns=['Torneo Fase', 'Casa', 'Trasferta', 'Gol Casa', 'Gol Trasferta', 'Vincitore'])
    if 'last_save' not in st.session_state:
        st.session_state['last_save'] = None

def parse_int(v):
    try:
        return int(v)
    except Exception:
        return None

def compute_standings(teams, matches_df):
    df = pd.DataFrame({'Squadra': teams}).dropna()
    df = df[df['Squadra'] != ''].reset_index(drop=True)
    stats = {t: {'Punti':0, 'PG':0, 'V':0, 'N':0, 'P':0, 'GF':0, 'GS':0} for t in df['Squadra']}

    for _, row in matches_df.iterrows():
        home = row.get('Squadra Casa')
        away = row.get('Squadra Trasferta')
        hg = parse_int(row.get('Gol Casa'))
        ag = parse_int(row.get('Gol Trasferta'))
        if not home or not away:
            continue
        if hg is None or ag is None:
            continue
        if home not in stats or away not in stats:
            continue
        stats[home]['PG'] += 1
        stats[away]['PG'] += 1
        stats[home]['GF'] += hg
        stats[home]['GS'] += ag
        stats[away]['GF'] += ag
        stats[away]['GS'] += hg
        if hg > ag:
            stats[home]['V'] += 1
            stats[away]['P'] += 1
            stats[home]['Punti'] += 3
        elif hg < ag:
            stats[away]['V'] += 1
            stats[home]['P'] += 1
            stats[away]['Punti'] += 3
        else:
            stats[home]['N'] += 1
            stats[away]['N'] += 1
            stats[home]['Punti'] += 1
            stats[away]['Punti'] += 1

    out = []
    for t in df['Squadra']:
        s = stats[t]
        dr = s['GF'] - s['GS']
        out.append({'Squadra': t, 'Punti': s['Punti'], 'PG': s['PG'], 'V': s['V'], 'N': s['N'], 'P': s['P'], 'GF': s['GF'], 'GS': s['GS'], 'DR': dr})
    out_df = pd.DataFrame(out)
    out_df = out_df.sort_values(by=['Punti','DR','GF'], ascending=[False,False,False]).reset_index(drop=True)
    return out_df

def parse_marcatori(matches_df):
    scorers = {}
    for _, row in matches_df.iterrows():
        mstr = row.get('Marcatori')
        if not isinstance(mstr, str) or mstr.strip() == '':
            continue
        parts = [p.strip() for p in mstr.split(';') if p.strip()]
        for p in parts:
            if '(' in p and ')' in p:
                try:
                    name = p[:p.rfind('(')].strip()
                    team = p[p.rfind('(')+1:p.rfind(')')].strip()
                except Exception:
                    continue
            else:
                name = p
                team = ''
            key = (name, team)
            scorers[key] = scorers.get(key, 0) + 1
    rows = [{'Giocatore': k[0], 'Squadra': k[1], 'Gol': v} for k,v in scorers.items()]
    if not rows:
        return pd.DataFrame(columns=['Giocatore','Squadra','Gol'])
    df = pd.DataFrame(rows).sort_values(by='Gol', ascending=False).reset_index(drop=True)
    return df

def add_sample_matches():
    if st.session_state['calendar'].empty:
        oggi = datetime.now().date()
        data_oggi = oggi.strftime('%Y-%m-%d')
        sample = pd.DataFrame([
            {'Giornata': 1, 'Data': data_oggi, 'Ora': '15:30', 'Luogo': 'Stadio A',
             'Squadra Casa': st.session_state['teams'][0] if st.session_state['teams'][0] else 'Squadra A',
             'Gol Casa': None,
             'Squadra Trasferta': st.session_state['teams'][1] if st.session_state['teams'][1] else 'Squadra B',
             'Gol Trasferta': None,
             'Marcatori': '', 'Cartellini': ''},
            {'Giornata': 1, 'Data': data_oggi, 'Ora': '17:00', 'Luogo': 'Stadio B',
             'Squadra Casa': st.session_state['teams'][2] if st.session_state['teams'][2] else 'Squadra C',
             'Gol Casa': None,
             'Squadra Trasferta': st.session_state['teams'][3] if st.session_state['teams'][3] else 'Squadra D',
             'Gol Trasferta': None,
             'Marcatori': '', 'Cartellini': ''}
        ])
        st.session_state['calendar'] = sample

def get_logo_img(team):
    if not team:
        return None
    logos = st.session_state.get('team_logos', {})
    img = logos.get(team)
    return img

def format_team_with_logo(team):
    logo = get_logo_img(team)
    if logo:
        # Resize or style can be added here
        return f'<img src="data:image/png;base64,{logo}" width="30" style="vertical-align:middle;margin-right:5px;"> {team}'
    else:
        return team

def to_base64(img_bytes):
    import base64
    return base64.b64encode(img_bytes).decode()

# --- Init session state ---------------------------------------------------
init_state()
add_sample_matches()

# --- Sidebar: Teams, Loghi, Import/Export --------------------------------
with st.sidebar:
    st.header('Impostazioni squadre e dati')
    st.markdown('Inserisci i nomi delle 20 squadre una per riga. Le righe vuote saranno ignorate.')
    teams_text = st.text_area('Nomi squadre (una per riga)', value='\n'.join(st.session_state['teams']), height=300)
    if st.button('Applica nomi squadre'):
        new_teams = [t.strip() for t in teams_text.splitlines()]
        while len(new_teams) < 20:
            new_teams.append('')
        new_teams = new_teams[:20]
        st.session_state['teams'] = new_teams
        # Reset logos dict keys if teams changed
        new_logos = {}
        for t in new_teams:
            if t in st.session_state['team_logos']:
                new_logos[t] = st.session_state['team_logos'][t]
            else:
                new_logos[t] = None
        st.session_state['team_logos'] = new_logos
        st.success('Nomi squadre aggiornati.')

    st.markdown('**Carica i loghi delle squadre (PNG o JPG, max 100KB):**')
    for team in st.session_state['teams']:
        if team:
            uploaded_logo = st.file_uploader(f'Logo per {team}', type=['png','jpg','jpeg'], key=f'logo_{team}')
            if uploaded_logo is not None:
                img_bytes = uploaded_logo.read()
                if len(img_bytes) > 100*1024:
                    st.error('File troppo grande, max 100KB')
                else:
                    st.session_state['team_logos'][team] = to_base64(img_bytes)
                    st.success(f'Logo caricato per {team}')

    st.markdown('**Backup / Ripristino dati**')
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Esporta JSON'):
            data = {
                'teams': st.session_state['teams'],
                'team_logos': st.session_state['team_logos'],
                'calendar': st.session_state['calendar'].to_dict(orient='records'),
                'knockout': st.session_state['knockout'].to_dict(orient='records')
            }
            st.download_button('Scarica JSON', json.dumps(data, ensure_ascii=False, indent=2), file_name='torneo_dati.json')
    with col2:
        uploaded = st.file_uploader('Carica JSON per ripristino', type=['json'])
        if uploaded is not None:
            try:
                j = json.load(uploaded)
                st.session_state['teams'] = j.get('teams', st.session_state['teams'])
                st.session_state['team_logos'] = j.get('team_logos', st.session_state['team_logos'])
                cal = pd.DataFrame(j.get('calendar', []))
                if not cal.empty:
                    st.session_state['calendar'] = cal
                ko = pd.DataFrame(j.get('knockout', []))
                if not ko.empty:
                    st.session_state['knockout'] = ko
                st.success('Dati ripristinati dal file JSON.')



