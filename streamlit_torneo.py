import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime

st.set_page_config(page_title="Torneo Calcio", layout="wide")

st.title("Torneo di Calcio — App gestionale (ITA)")
st.markdown("App semplice per gestire calendario, risultati, classifica, marcatori, cartellini e fase a eliminazione.")

# --- Helpers ---------------------------------------------------------------

def init_state():
    if 'teams' not in st.session_state:
        st.session_state['teams'] = ['' for _ in range(20)]
    if 'team_logos' not in st.session_state:
        st.session_state['team_logos'] = {t: None for t in st.session_state['teams']}
    if 'calendar' not in st.session_state:
        cols = ['Giornata', 'Data', 'Orario', 'Luogo', 'Squadra Casa', 'Gol Casa', 'Squadra Trasferta', 'Gol Trasferta', 'Marcatori', 'Cartellini']
        st.session_state['calendar'] = pd.DataFrame(columns=cols)
    if 'knockout' not in st.session_state:
        st.session_state['knockout'] = pd.DataFrame(columns=['Torneo Fase', 'Casa', 'Trasferta', 'Gol Casa', 'Gol Trasferta', 'Vincitore'])
    if 'current_round' not in st.session_state:
        st.session_state['current_round'] = 1
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
            # Format: "Nome Cognome (Squadra) [minuto']"
            name = p
            team = ''
            minute = None
            # Extract minute if present e.g. "[23']"
            import re
            m = re.search(r'\[(\d+)\']', p)
            if m:
                minute = int(m.group(1))
                name = p[:m.start()].strip()
            if '(' in name and ')' in name:
                try:
                    team = name[name.rfind('(')+1:name.rfind(')')].strip()
                    name = name[:name.rfind('(')].strip()
                except:
                    pass
            key = (name, team)
            scorers[key] = scorers.get(key, 0) + 1
    rows = [{'Giocatore': k[0], 'Squadra': k[1], 'Gol': v} for k,v in scorers.items()]
    if not rows:
        return pd.DataFrame(columns=['Giocatore','Squadra','Gol'])
    df = pd.DataFrame(rows).sort_values(by='Gol', ascending=False).reset_index(drop=True)
    return df

def parse_cartellini(matches_df):
    cards = {}
    for _, row in matches_df.iterrows():
        cstr = row.get('Cartellini')
        if not isinstance(cstr, str) or cstr.strip() == '':
            continue
        parts = [p.strip() for p in cstr.split(';') if p.strip()]
        for p in parts:
            # Format: "Nome Cognome (Squadra) [G|R] [minuto']" es. "Mario Rossi (Team) G [23']"
            import re
            minute = None
            card_type = None
            name = p
            team = ''
            # Extract minute
            mmin = re.search(r'\[(\d+)\']', p)
            if mmin:
                minute = int(mmin.group(1))
                name = name[:mmin.start()].strip()
            # Extract card type G or R
            mg = re.search(r'\b(G|R)\b', p)
            if mg:
                card_type = mg.group(1)
                name = re.sub(r'\b(G|R)\b', '', name).strip()
            # Extract team
            if '(' in name and ')' in name:
                try:
                    team = name[name.rfind('(')+1:name.rfind(')')].strip()
                    name = name[:name.rfind('(')].strip()
                except:
                    pass
            key = (name, team, card_type)
            cards[key] = cards.get(key, 0) + 1
    rows = [{'Giocatore': k[0], 'Squadra': k[1], 'Cartellino': k[2], 'Conteggio': v} for k,v in cards.items()]
    if not rows:
        return pd.DataFrame(columns=['Giocatore','Squadra','Cartellino','Conteggio'])
    df = pd.DataFrame(rows).sort_values(by=['Squadra','Cartellino','Conteggio'], ascending=[True,True,False]).reset_index(drop=True)
    return df

# --- Init session state ---------------------------------------------------
init_state()

# --- Sidebar: Teams, Loghi, Import Export ---------------------------------------
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

    st.markdown('Carica un logo per ogni squadra (formato PNG/JPEG, max 1MB):')
    for t in st.session_state['teams']:
        if t.strip() != '':
            logo_file = st.file_uploader(f'Logo {t}', type=['png','jpg','jpeg'], key=f'logo_{t}')
            if logo_file is not None:
                img_bytes = logo_file.read()
                st.session_state['team_logos'][t] = img_bytes

    st.markdown('**Backup / Ripristino dati**')
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Esporta JSON'):
            data = {
                'teams': st.session_state['teams'],
                'team_logos': {k: (v.hex() if v else None) for k,v in st.session_state['team_logos'].items()},
                'calendar': st.session_state['calendar'].to_dict(orient='records'),
                'knockout': st.session_state['knockout'].to_dict(orient='records'),
            }
            json_str = json.dumps(data)
            st.download_button('Scarica file JSON', json_str, file_name='torneo_backup.json', mime='application/json')
    with col2:
        upload_file = st.file_uploader('Carica backup JSON', type=['json'])
        if upload_file is not None:
            try:
                loaded = json.load(upload_file)
                st.session_state['teams'] = loaded.get('teams', st.session_state['teams'])
                # decode logos hex back to bytes
                loaded_logos = loaded.get('team_logos', {})
                for k,v in loaded_logos.items():
                    if v is not None:
                        st.session_state['team_logos'][k] = bytes.fromhex(v)
                    else:
                        st.session_state['team_logos'][k] = None
                st.session_state['calendar'] = pd.DataFrame(loaded.get('calendar', []))
                st.session_state['knockout'] = pd.DataFrame(loaded.get('knockout', []))
                st.success('Backup caricato con successo!')
            except Exception as e:
                st.error(f'Errore nel caricamento: {e}')

# --- Main area: menu e pagine ----------------------------------------------

pages = ["Giornata Corrente", "Calendario Completo", "Classifica", "Marcatori"]
page = st.radio("Naviga tra le pagine:", pages)

def render_match_details(row):
    st.write(f"**Data:** {row['Data']}  |  **Orario:** {row['Orario']}  |  **Luogo:** {row['Luogo']}")
    st.write(f"**Marcatori:** {row.get('Marcatori','-')}")
    st.write(f"**Cartellini:** {row.get('Cartellini','-')}")

def get_logo_img(team):
    if team in st.session_state['team_logos'] and st.session_state['team_logos'][team]:
        import base64
        b64 = base64.b64encode(st.session_state['team_logos'][team]).decode()
        return f'<img src="data:image/png;base64,{b64}" width="40" style="vertical-align:middle;margin-right:10px;">'
    else:
        return ''

if page == "Giornata Corrente":
    st.header("Partite della giornata corrente")

    if st.session_state['calendar'].empty:
        st.info("Nessuna partita inserita nel calendario.")
    else:
        giornate = sorted(st.session_state['calendar']['Giornata'].dropna().unique())
        if len(giornate) == 0:
            st.info("Nessuna giornata trovata nel calendario.")
        else:
            if 'giornata_corrente' not in st.session_state:
                st.session_state['giornata_corrente'] = giornate[0]
            giornata = st.selectbox("Seleziona giornata", giornate, index=giornate.index(st.session_state['giornata_corrente']))
            st.session_state['giornata_corrente'] = giornata
            partite = st.session_state['calendar'][st.session_state['calendar']['Giornata'] == giornata]

            if partite.empty:
                st.info(f"Nessuna partita registrata per la giornata {giornata}")
            else:
                for i, row in partite.iterrows():
                    col1, col2, col3, col4 = st.columns([1,1,1,4])
                    with col1:
                        logo_home = get_logo_img(row['Squadra Casa'])
                        st.markdown(f"{logo_home}**{row['Squadra Casa']}**", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"**{row['Gol Casa'] if pd.notna(row['Gol Casa']) else '-'}  :  {row['Gol Trasferta'] if pd.notna(row['Gol Trasferta']) else '-'}**")
                    with col3:
                        logo_away = get_logo_img(row['Squadra Trasferta'])
                        st.markdown(f"{logo_away}**{row['Squadra Trasferta']}**", unsafe_allow_html=True)
                    with col4:
                        with st.expander("Dettagli partita"):
                            render_match_details(row)

elif page == "Calendario Completo":
    st.header("Calendario completo")

    if st.session_state['calendar'].empty:
        st.info("Nessuna partita inserita nel calendario.")
    else:
        giornate = sorted(st.session_state['calendar']['Giornata'].dropna().unique())
        for giornata in giornate:
            st.subheader(f"Giornata {giornata}")
            partite = st.session_state['calendar'][st.session_state['calendar']['Giornata'] == giornata]
            for i, row in partite.iterrows():
                col1, col2, col3, col4 = st.columns([1,1,1,5])
                with col1:
                    logo_home = get_logo_img(row['Squadra Casa'])
                    st.markdown(f"{logo_home}**{row['Squadra Casa']}**", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"**{row['Gol Casa'] if pd.notna(row['Gol Casa']) else '-'}  :  {row['Gol Trasferta'] if pd.notna(row['Gol Trasferta']) else '-'}**")
                with col3:
                    logo_away = get_logo_img(row['Squadra Trasferta'])
                    st.markdown(f"{logo_away}**{row['Squadra Trasferta']}**", unsafe_allow_html=True)
                with col4:
                    with st.expander("Dettagli partita"):
                        render_match_details(row)

elif page == "Classifica":
    st.header("Classifica torneo")
    standings = compute_standings(st.session_state['teams'], st.session_state['calendar'])
    if standings.empty:
        st.info("Nessun dato per la classifica.")
    else:
        # Mostriamo anche il logo in tabella
        def render_logo(team):
            if team in st.session_state['team_logos'] and st.session_state['team_logos'][team]:
                import base64
                b64 = base64.b64encode(st.session_state['team_logos'][team]).decode()
                return f'<img src="data:image/png;base64,{b64}" width="25" style="vertical-align:middle;">'
            else:
                return ''
        df = standings.copy()
        df['Logo'] = df['Squadra'].apply(render_logo)
        # Ordine colonne
        cols_order = ['Logo','Squadra','Punti','PG','V','N','P','GF','GS','DR']
        df = df[cols_order]
        # Streamlit non rende HTML in dataframe, usiamo st.markdown + html table
        st.write("Classifica ordinata per punti, differenza reti e gol fatti.")
        from st_aggrid import AgGrid
        try:
            from st_aggrid import AgGrid
            from st_aggrid.grid_options_builder import GridOptionsBuilder
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_column('Logo', cellRenderer= "html")
            gb.configure_columns(['Squadra','Punti','PG','V','N','P','GF','GS','DR'], sortable=True)
            gridOptions = gb.build()
            AgGrid(df, gridOptions=gridOptions, fit_columns_on_grid_load=True)
        except ImportError:
            st.warning("Per vedere i loghi nella classifica, installa 'streamlit-aggrid' con: pip install streamlit-aggrid")
            st.dataframe(df.drop(columns='Logo'))

elif page == "Marcatori":
    st.header("Classifica marcatori")
    marcatori_df = parse_marcatori(st.session_state['calendar'])
    if marcatori_df.empty:
        st.info("Nessun marcatore registrato.")
    else:
        st.dataframe(marcatori_df)

# --- Form per inserire partite --------------------------------------------

with st.expander("Aggiungi / modifica partite"):
    st.markdown("Inserisci i dati delle partite. Marcatori e cartellini in questo formato (separati da ';'):")
    st.markdown("""
    - **Marcatori:** `Nome Cognome (Squadra) [minuto']` es. `Mario Rossi (Team A) [23']`; `Luca Bianchi (Team B)`
    - **Cartellini:** `Nome Cognome (Squadra) G [minuto']` per giallo, `Nome Cognome (Squadra) R [minuto']` per rosso, es. `Mario Rossi (Team A) G [45']`
    - Minuti sono opzionali.
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        nuova_giornata = st.number_input("Giornata", min_value=1, value=1, step=1, key='input_giornata')
        nuova_data = st.date_input("Data", key='input_data', value=datetime.today())
        nuovo_orario = st.text_input("Orario (es. 15:30)", key='input_orario', value="15:30")
    with col2:
        nuovo_luogo = st.text_input("Luogo", key='input_luogo', value="")
        squadra_casa = st.selectbox("Squadra Casa", options=[t for t in st.session_state['teams'] if t.strip() != ''], key='input_scasa')
        gol_casa = st.text_input("Gol Casa", key='input_golcasa', value="")
    with col3:
        squadra_trasferta = st.selectbox("Squadra Trasferta", options=[t for t in st.session_state['teams'] if t.strip() != ''], key='input_strasferta')
        gol_trasferta = st.text_input("Gol Trasferta", key='input_goltrasferta', value="")
        marcatori = st.text_area("Marcatori (separati da ';')", key='input_marcatori', height=80)
        cartellini = st.text_area("Cartellini (separati da ';')", key='input_cartellini', height=80)

    if st.button("Aggiungi / Aggiorna partita"):
        # Validazioni semplici
        if squadra_casa == squadra_trasferta:
            st.error("Le squadre Casa e Trasferta non possono essere uguali.")
        else:
            new_row = {
                'Giornata': nuova_giornata,
                'Data': nuova_data.strftime("%Y-%m-%d"),
                'Orario': nuovo_orario,
                'Luogo': nuovo_luogo,
                'Squadra Casa': squadra_casa,
                'Gol Casa': gol_casa if gol_casa != '' else None,
                'Squadra Trasferta': squadra_trasferta,
                'Gol Trasferta': gol_trasferta if gol_trasferta != '' else None,
                'Marcatori': marcatori,
                'Cartellini': cartellini,
            }
            # Se esiste partita uguale (giornata + squadre), aggiorna
            df = st.session_state['calendar']
            mask = (df['Giornata'] == nuova_giornata) & (df['Squadra Casa'] == squadra_casa) & (df['Squadra Trasferta'] == squadra_trasferta)
            if mask.any():
                idx = df.index[mask][0]
                for k,v in new_row.items():
                    st.session_state['calendar'].at[idx,k] = v
                st.success("Partita aggiornata.")
            else:
                st.session_state['calendar'] = pd.concat([df,pd.DataFrame([new_row])], ignore_index=True)
                st.success("Partita aggiunta.")

st.markdown("---")
st.markdown("© 2025 Torneo Calcio Streamlit App")





