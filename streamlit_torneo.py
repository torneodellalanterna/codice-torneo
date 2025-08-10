import streamlit as st
import pandas as pd
import io
import json
import base64
from datetime import datetime, timedelta

st.set_page_config(page_title="Torneo Calcio", layout="wide")

st.title("Torneo di Calcio — App gestionale (ITA)")
st.markdown("App semplice per gestire calendario, risultati, classifica, marcatori, cartellini e fase a eliminazione.")

# --- Helpers ---------------------------------------------------------------

def init_state():
    if 'teams' not in st.session_state:
        st.session_state['teams'] = ['' for _ in range(20)]
    if 'logos' not in st.session_state:
        # logos dict: team_name -> base64 image string
        st.session_state['logos'] = {}
    if 'calendar' not in st.session_state:
        # Added columns: Giornata, Ora, Luogo, Cartellini (string)
        cols = ['Giornata', 'Data', 'Ora', 'Luogo', 'Squadra Casa', 'Gol Casa', 'Squadra Trasferta', 'Gol Trasferta', 'Marcatori', 'Cartellini']
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

def parse_cartellini(matches_df):
    # Cartellini formato: "Nome Giocatore (Squadra) G 12; Altro Giocatore (Squadra) R 45"
    # Dove G = giallo, R = rosso, numero opzionale minuto
    cards = {}
    for _, row in matches_df.iterrows():
        cstr = row.get('Cartellini')
        if not isinstance(cstr, str) or cstr.strip() == '':
            continue
        parts = [p.strip() for p in cstr.split(';') if p.strip()]
        for p in parts:
            # Es: "Mario Rossi (Team A) G 12" oppure "Luca Bianchi (Team B) R"
            tokens = p.split()
            if len(tokens) < 2:
                continue
            # Recupero nome e squadra tra parentesi
            name_team = ' '.join(tokens[:-2]) if len(tokens) >=3 else ' '.join(tokens[:-1])
            # estraggo nome e squadra
            if '(' in name_team and ')' in name_team:
                try:
                    name = name_team[:name_team.rfind('(')].strip()
                    team = name_team[name_team.rfind('(')+1:name_team.rfind(')')].strip()
                except Exception:
                    continue
            else:
                name = name_team
                team = ''
            card_type = tokens[-2] if len(tokens) >=3 else tokens[-1]
            key = (name, team)
            if key not in cards:
                cards[key] = {'G':0, 'R':0}
            if card_type.upper() == 'G':
                cards[key]['G'] += 1
            elif card_type.upper() == 'R':
                cards[key]['R'] += 1
    # Converto in dataframe
    rows = []
    for k,v in cards.items():
        rows.append({'Giocatore': k[0], 'Squadra': k[1], 'Gialli': v['G'], 'Rossi': v['R']})
    if not rows:
        return pd.DataFrame(columns=['Giocatore','Squadra','Gialli','Rossi'])
    df = pd.DataFrame(rows).sort_values(by=['Rossi','Gialli'], ascending=[False,False]).reset_index(drop=True)
    return df

def get_logo_img(team_name, width=40):
    if team_name in st.session_state['logos']:
        img_b64 = st.session_state['logos'][team_name]
        return f'<img src="data:image/png;base64,{img_b64}" width="{width}" style="vertical-align:middle;margin-right:8px;border-radius:4px;">'
    return ''

def render_team_with_logo(team_name):
    logo_html = get_logo_img(team_name)
    if team_name == '' or team_name is None:
        return ''
    return f'{logo_html}<span>{team_name}</span>'

def giornata_corrente(df_calendar):
    # Restituisce il numero giornata più vicina alla data odierna con partite non ancora terminate
    if df_calendar.empty:
        return None
    oggi = datetime.now().date()
    df_calendar['Data_dt'] = pd.to_datetime(df_calendar['Data'], errors='coerce').dt.date
    # Cerco la giornata con partite >= oggi
    future_days = df_calendar[df_calendar['Data_dt'] >= oggi]
    if not future_days.empty:
        return future_days['Giornata'].min()
    # Se nessuna partita futura, prendo l'ultima giornata giocata
    past_days = df_calendar[df_calendar['Data_dt'] < oggi]
    if not past_days.empty:
        return past_days['Giornata'].max()
    return None

def safe_html(text):
    import html
    return html.escape(str(text))

# --- Init session state ---------------------------------------------------
init_state()

# --- Sidebar: Teams / Logos / Import Export --------------------------------
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
        st.success('Nomi squadre aggiornati.')

    st.markdown('**Carica loghi squadre (PNG/JPG, max 200KB)**')
    uploaded_logos = st.file_uploader('Carica immagini singole (nome file = nome squadra)', accept_multiple_files=True, type=['png','jpg','jpeg'])
    if uploaded_logos:
        count = 0
        for file in uploaded_logos:
            team_name = file.name.rsplit('.', 1)[0].strip()
            if team_name not in st.session_state['teams']:
                st.warning(f'Attenzione: nome file "{file.name}" non corrisponde a nessuna squadra.')
                continue
            bytes_img = file.read()
            if len(bytes_img) > 200*1024:
                st.warning(f'Immagine {file.name} troppo grande (>200KB), ignorata.')
                continue
            b64 = base64.b64encode(bytes_img).decode()
            st.session_state['logos'][team_name] = b64
            count += 1
        if count > 0:
            st.success(f'Caricati {count} loghi.')

    st.markdown('**Backup / Ripristino dati**')
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Esporta JSON'):
            data = {
                'teams': st.session_state['teams'],
                'logos': st.session_state['logos'],
                'calendar': st.session_state['calendar'].to_json(orient='records'),
                'knockout': st.session_state['knockout'].to_json(orient='records'),
            }
            st.download_button('Scarica backup JSON', data=json.dumps(data), file_name='torneo_backup.json')
    with col2:
        upload_backup = st.file_uploader('Carica backup JSON', type=['json'])
        if upload_backup:
            try:
                data = json.load(upload_backup)
                st.session_state['teams'] = data.get('teams', st.session_state['teams'])
                st.session_state['logos'] = data.get('logos', st.session_state['logos'])
                st.session_state['calendar'] = pd.read_json(data.get('calendar', '[]'), orient='records')
                st.session_state['knockout'] = pd.read_json(data.get('knockout', '[]'), orient='records')
                st.success('Backup caricato correttamente.')
            except Exception as e:
                st.error(f'Errore nel caricamento backup: {e}')

# --- Main navigation -------------------------------------------------------
page = st.sidebar.radio("Seleziona pagina", ["Home - Partite Oggi", "Classifica", "Calendario", "Fase a Eliminazione", "Admin"])

# --- Home page: partite giornata corrente -----------------------------------
if page == "Home - Partite Oggi":
    st.header("Partite della giornata corrente")
    cal = st.session_state['calendar']
    if cal.empty:
        st.info("Nessuna partita inserita.")
    else:
        g_corr = giornata_corrente(cal)
        if g_corr is None:
            st.info("Nessuna partita programmata.")
        else:
            st.subheader(f"Giornata {g_corr}")
            df_giornata = cal[cal['Giornata'] == g_corr].copy()
            if df_giornata.empty:
                st.info("Nessuna partita in programma per la giornata corrente.")
            else:
                for idx, row in df_giornata.iterrows():
                    casa = row['Squadra Casa']
                    trasf = row['Squadra Trasferta']
                    logo_casa = get_logo_img(casa, 50)
                    logo_trasf = get_logo_img(trasf, 50)
                    data = row['Data']
                    ora = row['Ora']
                    luogo = row['Luogo']
                    gol_casa = row['Gol Casa']
                    gol_trasf = row['Gol Trasferta']
                    marcatori = row.get('Marcatori', '')
                    cartellini = row.get('Cartellini', '')

                    col1, col2, col3 = st.columns([2,1,2])
                    with col1:
                        st.markdown(f"{logo_casa} **{safe_html(casa)}**", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"**{gol_casa if pd.notna(gol_casa) else '-'} : {gol_trasf if pd.notna(gol_trasf) else '-'}**")
                        st.markdown(f"{data} {ora}")
                        st.markdown(f"*{luogo}*")
                    with col3:
                        st.markdown(f"{logo_trasf} **{safe_html(trasf)}**", unsafe_allow_html=True)

                    with st.expander("Dettagli partita"):
                        st.markdown("**Marcatori:**")
                        st.write(marcatori if marcatori else "Nessun marcatore")
                        st.markdown("**Cartellini:**")
                        st.write(cartellini if cartellini else "Nessun cartellino")
                    st.markdown("---")

# --- Classifica -------------------------------------------------------------
elif page == "Classifica":
    st.header("Classifica generale")
    standings = compute_standings(st.session_state['teams'], st.session_state['calendar'])
    if standings.empty:
        st.info("Inserisci risultati nel calendario per visualizzare la classifica.")
    else:
        # Mostro con logo e nome squadra
        def format_team(t):
            logo_html = get_logo_img(t, 30)
            return f'{logo_html}<span>{t}</span>'
        standings_html = standings.copy()
        standings_html['Squadra'] = standings_html['Squadra'].apply(lambda x: format_team(x))
        st.write(standings_html.to_html(escape=False, index=False), unsafe_allow_html=True)

# --- Calendario -------------------------------------------------------------
elif page == "Calendario":
    st.header("Gestione Calendario e risultati")
    cal = st.session_state['calendar']
    n = st.number_input("Numero di partite da mostrare/modificare", min_value=0, max_value=200, value=len(cal))
    if n != len(cal):
        cal = cal.reindex(range(n))
        st.session_state['calendar'] = cal
    if n > 0:
        edited = []
        for i in range(n):
            with st.expander(f"Partita {i+1}"):
                cols = st.columns(10)
                giornata = cols[0].number_input("Giornata", min_value=1, value=int(cal.at[i,'Giornata']) if i < len(cal) and pd.notna(cal.at[i,'Giornata']) else 1, key=f"giornata_{i}")
                data = cols[1].date_input("Data", value=cal.at[i,'Data'] if i < len(cal) and pd.notna(cal.at[i,'Data']) else datetime.now().date(), key=f"data_{i}")
                ora = cols[2].text_input("Ora (HH:MM)", value=cal.at[i,'Ora'] if i < len(cal) else "", key=f"ora_{i}")
                luogo = cols[3].text_input("Luogo", value=cal.at[i,'Luogo'] if i < len(cal) else "", key=f"luogo_{i}")
                casa = cols[4].selectbox("Squadra Casa", st.session_state['teams'], index=st.session_state['teams'].index(cal.at[i,'Squadra Casa']) if i < len(cal) and cal.at[i,'Squadra Casa'] in st.session_state['teams'] else 0, key=f"casa_{i}")
                gol_casa = cols[5].text_input("Gol Casa", value=str(cal.at[i,'Gol Casa']) if i < len(cal) and pd.notna(cal.at[i,'Gol Casa']) else "", key=f"g_casa_{i}")
                trasf = cols[6].selectbox("Squadra Trasferta", st.session_state['teams'], index=st.session_state['teams'].index(cal.at[i,'Squadra Trasferta']) if i < len(cal) and cal.at[i,'Squadra Trasferta'] in st.session_state['teams'] else 0, key=f"trasf_{i}")
                gol_trasf = cols[7].text_input("Gol Trasferta", value=str(cal.at[i,'Gol Trasferta']) if i < len(cal) and pd.notna(cal.at[i,'Gol Trasferta']) else "", key=f"g_trasf_{i}")
                marcatori = cols[8].text_area("Marcatori (es: Mario Rossi (Team A); Luca Bianchi (Team B))", value=cal.at[i,'Marcatori'] if i < len(cal) else "", height=50, key=f"marcatori_{i}")
                cartellini = cols[9].text_area("Cartellini (es: Mario Rossi (Team A) G 12; Luca Bianchi (Team B) R)", value=cal.at[i].get('Cartellini','') if i < len(cal) else "", height=50, key=f"cartellini_{i}")

                # Salvo
                cal.at[i,'Giornata'] = giornata
                cal.at[i,'Data'] = data
                cal.at[i,'Ora'] = ora
                cal.at[i,'Luogo'] = luogo
                cal.at[i,'Squadra Casa'] = casa
                cal.at[i,'Gol Casa'] = gol_casa if gol_casa.strip() != '' else None
                cal.at[i,'Squadra Trasferta'] = trasf
                cal.at[i,'Gol Trasferta'] = gol_trasf if gol_trasf.strip() != '' else None
                cal.at[i,'Marcatori'] = marcatori
                cal.at[i,'Cartellini'] = cartellini

        st.session_state['calendar'] = cal
        st.success("Calendario aggiornato.")

# --- Fase a Eliminazione ---------------------------------------------------
elif page == "Fase a Eliminazione":
    st.header("Fase a Eliminazione")
    df = st.session_state['knockout']
    n = st.number_input("Numero di partite in eliminazione", min_value=0, max_value=100, value=len(df))
    if n != len(df):
        df = df.reindex(range(n))
        st.session_state['knockout'] = df
    if n > 0:
        for i in range(n):
            with st.expander(f"Partita Eliminazione {i+1}"):
                cols = st.columns(5)
                fase = cols[0].text_input("Fase torneo (es. Quarti, Semifinale)", value=df.at[i,'Torneo Fase'] if i < len(df) and pd.notna(df.at[i,'Torneo Fase']) else "", key=f"fase_{i}")
                casa = cols[1].selectbox("Squadra Casa", st.session_state['teams'], index=st.session_state['teams'].index(df.at[i,'Casa']) if i < len(df) and df.at[i,'Casa'] in st.session_state['teams'] else 0, key=f"k_casa_{i}")
                trasf = cols[2].selectbox("Squadra Trasferta", st.session_state['teams'], index=st.session_state['teams'].index(df.at[i,'Trasferta']) if i < len(df) and df.at[i,'Trasferta'] in st.session_state['teams'] else 0, key=f"k_trasf_{i}")
                gol_casa = cols[3].text_input("Gol Casa", value=str(df.at[i,'Gol Casa']) if i < len(df) and pd.notna(df.at[i,'Gol Casa']) else "", key=f"k_g_casa_{i}")
                gol_trasf = cols[4].text_input("Gol Trasferta", value=str(df.at[i,'Gol Trasferta']) if i < len(df) and pd.notna(df.at[i,'Gol Trasferta']) else "", key=f"k_g_trasf_{i}")

                df.at[i,'Torneo Fase'] = fase
                df.at[i,'Casa'] = casa
                df.at[i,'Trasferta'] = trasf
                df.at[i,'Gol Casa'] = gol_casa if gol_casa.strip() != '' else None
                df.at[i,'Gol Trasferta'] = gol_trasf if gol_trasf.strip() != '' else None
                # Calcolo vincitore se possibile
                gc = parse_int(df.at[i,'Gol Casa'])
                gt = parse_int(df.at[i,'Gol Trasferta'])
                if gc is not None and gt is not None:
                    if gc > gt:
                        df.at[i,'Vincitore'] = casa
                    elif gt > gc:
                        df.at[i,'Vincitore'] = trasf
                    else:
                        df.at[i,'Vincitore'] = "Pareggio"
                else:
                    df.at[i,'Vincitore'] = None
        st.session_state['knockout'] = df
        st.success("Fase a eliminazione aggiornata.")

# --- Fine ---------------------------------------------------


