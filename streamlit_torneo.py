import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime

st.set_page_config(page_title="Torneo Calcio", layout="wide")

st.title("Torneo di Calcio — App gestionale (ITA)")
st.markdown("App semplice per gestire calendario, risultati, classifica, marcatori e fase a eliminazione.")

# --- Helpers ---------------------------------------------------------------

def init_state():
    if 'teams' not in st.session_state:
        st.session_state['teams'] = ['' for _ in range(20)]
    if 'calendar' not in st.session_state:
        cols = ['Data', 'Squadra Casa', 'Gol Casa', 'Squadra Trasferta', 'Gol Trasferta', 'Marcatori']
        st.session_state['calendar'] = pd.DataFrame(columns=cols)
    if 'knockout' not in st.session_state:
        # default empty bracket (quarterfinals: 8 teams -> 4 matches)
        st.session_state['knockout'] = pd.DataFrame(columns=['Torneo Fase', 'Casa', 'Trasferta', 'Gol Casa', 'Gol Trasferta', 'Vincitore'])
    if 'last_save' not in st.session_state:
        st.session_state['last_save'] = None


def parse_int(v):
    try:
        return int(v)
    except Exception:
        return None


def compute_standings(teams, matches_df):
    # init table
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

    # Verifica che tutte le colonne per ordinamento esistano
    for col in ['Punti', 'DR', 'GF']:
        if col not in out_df.columns:
            out_df[col] = 0

    out_df = out_df.sort_values(by=['Punti','DR','GF'], ascending=[False,False,False]).reset_index(drop=True)
    return out_df


def parse_marcatori(matches_df):
    # expects marcatori as semicolon-separated entries like: "Mario Rossi (Squadra A); Luca Bianchi (Squadra B)"
    scorers = {}
    for _, row in matches_df.iterrows():
        mstr = row.get('Marcatori')
        if not isinstance(mstr, str) or mstr.strip() == '':
            continue
        parts = [p.strip() for p in mstr.split(';') if p.strip()]
        for p in parts:
            # try to extract "Name (Team)"
            if '(' in p and ')' in p:
                try:
                    name = p[:p.rfind('(')].strip()
                    team = p[p.rfind('(')+1:p.rfind(')')].strip()
                except Exception:
                    continue
            else:
                # fallback: only name known
                name = p
                team = ''
            key = (name, team)
            scorers[key] = scorers.get(key, 0) + 1
    # convert to dataframe
    rows = [{'Giocatore': k[0], 'Squadra': k[1], 'Gol': v} for k,v in scorers.items()]
    if not rows:
        return pd.DataFrame(columns=['Giocatore','Squadra','Gol'])
    df = pd.DataFrame(rows).sort_values(by='Gol', ascending=False).reset_index(drop=True)
    return df


# --- Init session state ---------------------------------------------------
init_state()

# --- Sidebar: Teams / Import Export ---------------------------------------
with st.sidebar:
    st.header('Impostazioni squadre e dati')
    st.markdown('Inserisci i nomi delle 20 squadre una per riga. Le righe vuote saranno ignorate.')
    teams_text = st.text_area('Nomi squadre (una per riga)', value='\n'.join(st.session_state['teams']), height=300)
    if st.button('Applica nomi squadre'):
        new_teams = [t.strip() for t in teams_text.splitlines()]
        # pad or trim to 20
        while len(new_teams) < 20:
            new_teams.append('')
        new_teams = new_teams[:20]
        st.session_state['teams'] = new_teams
        st.success('Nomi squadre aggiornati.')

    st.markdown('**Backup / Ripristino dati**')
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Esporta JSON'):
            data = {
                'teams': st.session_state['teams'],
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
                cal = pd.DataFrame(j.get('calendar', []))
                if not cal.empty:
                    st.session_state['calendar'] = cal
                ko = pd.DataFrame(j.get('knockout', []))
                if not ko.empty:
                    st.session_state['knockout'] = ko
                st.success('Dati ripristinati dal file JSON.')
            except Exception as e:
                st.error('Errore nel leggere il file JSON: ' + str(e))

    st.markdown('**Import/Export CSV (calendario)**')
    upcsv = st.file_uploader('Import calendario (CSV)', type=['csv'], key='importcal')
    if upcsv is not None:
        try:
            cal = pd.read_csv(upcsv)
            st.session_state['calendar'] = cal
            st.success('Calendario importato dal CSV.')
        except Exception as e:
            st.error('Errore import CSV: ' + str(e))
    if st.button('Esporta calendario (CSV)'):
        buf = st.session_state['calendar'].to_csv(index=False)
        st.download_button('Scarica calendario CSV', buf, file_name='calendario.csv')

    st.markdown("""Aiuto: i marcatori devono essere inseriti nel formato:
Nome Cognome (Squadra); Altro Giocatore (Altro Team)
separati da punto e virgola. Ogni voce conta come 1 gol.""")

# --- Main: Tabs -----------------------------------------------------------

tabs = st.tabs(['Calendario e risultati', 'Classifica', 'Marcatori', 'Eliminazione diretta'])

# --- Calendario e risultati -----------------------------------------------
with tabs[0]:
    st.header('Calendario e inserimento risultati')
    st.markdown("Aggiungi le partite nell'ordine che preferisci. Per aggiornare classifica e marcatori, premi \"Salva calendario\".")
    cal = st.session_state['calendar']
    # ensure columns
    required_cols = ['Data', 'Squadra Casa', 'Gol Casa', 'Squadra Trasferta', 'Gol Trasferta', 'Marcatori']
    for c in required_cols:
        if c not in cal.columns:
            cal[c] = ''
    edited = st.data_editor(cal, num_rows='dynamic', use_container_width=True)
    if st.button('Salva calendario'):
        st.session_state['calendar'] = edited
        st.session_state['last_save'] = datetime.utcnow().isoformat()
        st.success('Calendario salvato.')

# --- Classifica -----------------------------------------------------------
with tabs[1]:
    st.header('Classifica')
    st.markdown('Classifica calcolata automaticamente: Punti → Differenza reti → Gol fatti')
    standings = compute_standings(st.session_state['teams'], st.session_state['calendar'])
    st.dataframe(standings)
    if st.button('Aggiorna classifica'):
        st.experimental_rerun()

# --- Marcatori ------------------------------------------------------------
with tabs[2]:
    st.header('Marcatori')
    scorers = parse_marcatori(st.session_state['calendar'])
    st.dataframe(scorers)
    if scorers.empty:
        st.info('Nessun marcatore registrato. Inserisci i nomi nella colonna "Marcatori" del calendario (es: Mario Rossi (Team A); Luca Bianchi (Team B)).')

# --- Eliminazione diretta ------------------------------------------------
with tabs[3]:
    st.header('Fase a eliminazione diretta')
    st.markdown('Crea la tabella della fase ad eliminazione (es: Quarti -> Semifinali -> Finale). Inserisci le squadre manualmente o copia dalla classifica.')
    ko = st.session_state['knockout']
    if ko.empty:
        # create 4 default quarti vuoti
        ko = pd.DataFrame([{'Torneo Fase':'Quarti','Casa':'','Trasferta':'','Gol Casa':'','Gol Trasferta':'','Vincitore':''} for _ in range(4)])
        st.session_state['knockout'] = ko
    edited_ko = st.data_editor(ko, num_rows='dynamic', use_container_width=True)
    if st.button('Salva eliminazione diretta'):
        st.session_state['knockout'] = edited_ko
        st.success('Tabella eliminazione salvata.')
    # compute winners
    display_ko = st.session_state['knockout'].copy()
    winners = []
    for idx, r in display_ko.iterrows():
        hg = parse_int(r.get('Gol Casa'))
        ag = parse_int(r.get('Gol Trasferta'))
        if hg is None or ag is None:
            winners.append('')
        else:
            if hg > ag:
                winners.append(r.get('Casa'))
            elif ag > hg:
                winners.append(r.get('Trasferta'))
            else:
                winners.append('Pareggio (decidi manualmente)')
    display_ko['Vincitore'] = winners
    st.markdown('Risultati permettono di vedere automaticamente il vincitore (in caso di pareggio, decidere manualmente).')
    st.dataframe(display_ko)

# --- Footer / info --------------------------------------------------------
st.markdown('---')
col1, col2 = st.columns([2,1])
with col1:
    st.caption('Suggerimenti:')
    st.markdown('- Per mobilità: apri l\'app su smartphone e modifica il calendario con la data e i risultati.\n- Per salvare uno storico, usa il pulsante "Esporta JSON" dalla sidebar oppure scarica il CSV del calendario.')
with col2:
    if st.session_state['last_save']:
        st.caption(f"Ultimo salvataggio: {st.session_state['last_save']}")
    else:
        st.caption('Nessun salvataggio ancora eseguito.')

st.info('Se vuoi che io adatti il formato dei marcatori o aggiunga funzionalità (es: conteggio autogol, rigori, statistica giocatore), dimmelo e lo aggiorno.')
