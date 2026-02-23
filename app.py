import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import urllib.parse
import requests
import base64
import hashlib
from io import BytesIO
from PIL import Image
from supabase import create_client, Client
import traceback

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered", initial_sidebar_state="collapsed") 
fuso_local = timezone(timedelta(hours=-3))

# --- 2. CONEXÃO COM O SUPABASE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("⚠️ Chaves do Supabase não encontradas no st.secrets!")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"Erro ao conectar com o Banco de Dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES DO GOOGLE LOGIN ---
GOOGLE_CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = st.secrets.get("REDIRECT_URI", "http://localhost:8501") 

def gerar_url_google():
    client_id_limpo = str(GOOGLE_CLIENT_ID).strip().replace('"', '').replace("'", "")
    redirect_limpo = str(REDIRECT_URI).strip().replace('"', '').replace("'", "")
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": client_id_limpo,
        "response_type": "code",
        "redirect_uri": redirect_limpo,
        "scope": "openid email profile",
        "prompt": "select_account"
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"

GOOGLE_SVG = """
<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" style="width:20px;height:20px;margin-right:10px;">
<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"></path>
<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"></path>
<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"></path>
<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"></path>
</svg>
"""

# --- 4. FUNÇÕES DE BANCO DE DADOS ---
def hash_senha(senha):
    return hashlib.sha256(str.encode(senha)).hexdigest()

def validar_login(username, senha):
    try:
        res = supabase.table('users').select('*').eq('username', username).execute()
        if len(res.data) > 0:
            user = res.data[0]
            if user.get('senha') == hash_senha(senha) or user.get('senha') == "google_sso_senha_dummy":
                return user
    except Exception as e: pass
    return None

def criar_conta(username, nome, senha):
    try:
        res = supabase.table('users').select('username').eq('username', username).execute()
        if len(res.data) > 0: return False 
        
        novo_perfil = {"idade": 30, "peso": 70.0, "altura": 170, "objetivo": "Emagrecimento Saudável", "atividade": "Moderadamente Ativo", "foto": None, "streak": 1, "last_login": "", "historico_peso": [], "plano": "gratis"}
        supabase.table('users').insert({"username": username, "nome": nome, "senha": hash_senha(senha), "perfil": novo_perfil}).execute()
        return True
    except Exception as e: return False

def salvar_perfil(username, nome_atualizado, perfil_data):
    try: supabase.table('users').update({"nome": nome_atualizado, "perfil": perfil_data}).eq('username', username).execute()
    except Exception as e: pass

def carregar_despensa(username):
    try:
        res = supabase.table('despensa').select('*').eq('username', username).execute()
        if len(res.data) > 0:
            df = pd.DataFrame(res.data)
            if 'quantidade' in df.columns:
                df['quantidade'] = pd.to_numeric(df['quantidade'], errors='coerce').fillna(0)
            df = df.rename(columns={"alimento": "Alimento", "quantidade": "Quantidade", "unidade": "Unidade", "pronto_rapido": "Pronto/Rápido"})
            colunas_necessarias = ['Alimento', 'Quantidade', 'Unidade', 'Pronto/Rápido']
            for col in colunas_necessarias:
                if col not in df.columns:
                    df[col] = "" if col != 'Quantidade' else 0.0
            return df[colunas_necessarias]
    except Exception as e: pass
    
    df_padrao = pd.DataFrame({"Alimento": ["Ovos", "Aveia", "Frango"], "Quantidade": [12.0, 500.0, 1000.0], "Unidade": ["un", "g", "g"], "Pronto/Rápido": ["Sim", "Sim", "Não"]})
    return df_padrao

def salvar_despensa(df, username):
    try:
        supabase.table('despensa').delete().eq('username', username).execute()
        if not df.empty:
            df_db = df.rename(columns={"Alimento": "alimento", "Quantidade": "quantidade", "Unidade": "unidade", "Pronto/Rápido": "pronto_rapido"})
            df_db['username'] = username
            records = df_db.to_dict(orient='records')
            for r in records: r['quantidade'] = float(r.get('quantidade', 0))
            supabase.table('despensa').insert(records).execute()
    except Exception as e: pass

def extrair_numero(texto):
    numeros = re.findall(r'\d+', str(texto))
    return int(numeros[0]) if numeros else 0

def safe_int(valor, padrao):
    try: return int(valor) if valor is not None else padrao
    except: return padrao

def safe_float(valor, padrao):
    try: return float(valor) if valor is not None else padrao
    except: return padrao

# --- 5. VERIFICAÇÃO DE API GEMINI ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        modelo = genai.GenerativeModel('gemini-1.5-flash') 
        api_configurada = True
    except Exception as e: pass

# --- 6. INICIALIZAÇÃO DE SESSÃO ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = None
if 'nome_usuario' not in st.session_state: st.session_state.nome_usuario = None
if 'perfil' not in st.session_state: st.session_state.perfil = {}
if 'despensa' not in st.session_state: st.session_state.despensa = pd.DataFrame()
if 'cardapio_atual' not in st.session_state: st.session_state.cardapio_atual = None
if 'cardapio_ideal' not in st.session_state: st.session_state.cardapio_ideal = None
if 'consumidos' not in st.session_state: st.session_state.consumidos = set()
if 'chat_history' not in st.session_state: st.session_state.chat_history = []

def fazer_logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.query_params.clear() 
    st.rerun()

# --- INTERCEPTADOR DO GOOGLE (COM FEEDBACK VISUAL) ---
if not st.session_state.logged_in and "code" in st.query_params:
    st.info("🔄 Autenticando com o Google... Preparando seu painel.")
    codigo_autorizacao = st.query_params["code"]
    client_id_limpo = str(GOOGLE_CLIENT_ID).strip().replace('"', '').replace("'", "")
    client_secret_limpo = str(GOOGLE_CLIENT_SECRET).strip().replace('"', '').replace("'", "")
    redirect_limpo = str(REDIRECT_URI).strip().replace('"', '').replace("'", "")
    
    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {"code": codigo_autorizacao, "client_id": client_id_limpo, "client_secret": client_secret_limpo, "redirect_uri": redirect_limpo, "grant_type": "authorization_code"}
        res = requests.post(token_url, data=token_data)
        if res.status_code == 200:
            access_token = res.json().get("access_token")
            user_res = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if user_res.status_code == 200:
                google_user = user_res.json()
                username_google = google_user.get("email") 
                nome_google = google_user.get("given_name", "Usuário") 
                
                try:
                    res_db = supabase.table('users').select('*').eq('username', username_google).execute()
                    if len(res_db.data) == 0:
                        criar_conta(username_google, nome_google, "google_sso_senha_dummy")
                        res_db = supabase.table('users').select('*').eq('username', username_google).execute()
                    
                    user_db = res_db.data[0]
                    st.session_state.logged_in = True
                    st.session_state.username = username_google
                    st.session_state.nome_usuario = user_db.get('nome', 'Usuário')
                    
                    perfil_carregado = user_db.get("perfil")
                    st.session_state.perfil = perfil_carregado if isinstance(perfil_carregado, dict) else {}
                    st.session_state.despensa = carregar_despensa(username_google)
                except Exception as e: pass
                st.query_params.clear()
                st.rerun()
        else:
            st.query_params.clear()
    except Exception as e: pass

# --- 7. CSS ADAPTATIVO ---
st.markdown(f"""
    <style>
    :root {{ --bg-color: #F2F2F7; --card-bg: #FFFFFF; --border-color: #E5E5EA; --input-bg: #FAFAFA; --text-primary: #000000; --shadow-color: rgba(0, 0, 0, 0.04); --pro-color: #FFD700; }}
    @media (prefers-color-scheme: dark) {{
        :root {{ --bg-color: #0E1117; --card-bg: #262730; --border-color: #333333; --input-bg: #1A1C23; --text-primary: #FAFAFA; --shadow-color: rgba(0, 0, 0, 0.3); }}
    }}

    [data-testid="stSidebar"] {{ display: none !important; }}
    [data-testid="collapsedControl"] {{ display: none !important; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
    .block-container {{padding-top: 1rem; padding-bottom: 5rem; max-width: 600px;}}
    .stApp {{ background-color: var(--bg-color) !important; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Helvetica, Arial, sans-serif !important; }}
    
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        background-color: var(--card-bg) !important; border-radius: 14px !important; border: 1px solid var(--border-color) !important; box-shadow: 0px 2px 10px var(--shadow-color) !important; padding: 15px !important;
    }}
    
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {{
        border: 1px solid var(--border-color) !important; border-radius: 10px !important; padding: 12px 14px !important; background-color: var(--input-bg) !important; color: var(--text-primary) !important;
    }}
    
    div[data-testid="stButton"] button, div[data-testid="stPopover"] > button {{
        border-radius: 20px !important; height: 45px !important; font-weight: 600 !important; font-size: 16px !important; border: 1px solid var(--border-color) !important; transition: all 0.2s ease-in-out !important; background-color: var(--card-bg) !important; color: var(--text-primary) !important;
    }}
    div[data-testid="stButton"] button[kind="primary"] {{ background-color: #007AFF !important; color: white !important; border: none !important; }}
    
    .btn-google-nativo {{
        display: flex; align-items: center; justify-content: center; background-color: var(--card-bg); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 20px; height: 50px; font-weight: 600; font-size: 16px; text-decoration: none; width: 100%; transition: all 0.2s ease-in-out; box-shadow: 0 1px 3px var(--shadow-color);
    }}
    
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th {{ color: #8E8E93 !important; font-weight: 600 !important; border-bottom: 1px solid var(--border-color) !important; text-align: left !important; padding-bottom: 8px !important; }}
    td, th {{ padding: 12px 8px !important; border-bottom: 1px solid var(--border-color) !important; border-top: none !important; border-left: none !important; border-right: none !important; color: var(--text-primary) !important; }}
    tr:last-child td {{ border-bottom: none !important; }}
    
    .macro-bar-container {{ width: 100%; background-color: var(--border-color); border-radius: 8px; height: 10px; margin-top: 4px; overflow: hidden; }}
    .macro-bar-fill {{ height: 100%; border-radius: 8px; transition: width 0.5s ease-in-out; }}
    .bg-kcal {{ background-color: #FF9500; }} .bg-prot {{ background-color: #34C759; }} .bg-carb {{ background-color: #007AFF; }} .bg-gord {{ background-color: #AF52DE; }}

    div[data-testid="stTabs"] > div:first-child {{
        position: -webkit-sticky; position: sticky; top: 0px; z-index: 999; background-color: var(--bg-color); backdrop-filter: blur(10px); padding-top: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); overflow-x: auto;
    }}
    
    .adapt-text {{ color: var(--text-primary) !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# MÓDULO 1: TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    st.markdown("""
        <div style="text-align: center; margin-bottom: 25px; margin-top: 20px;">
            <h1 style="font-size: 4rem; margin-bottom: 0;">🍏</h1>
            <h1 class="adapt-text" style="font-weight: 800;">NutryAi</h1>
            <p style="color: #8E8E93;">Sua rotina flexível.</p>
        </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        login_user = st.text_input("Usuário", placeholder="ex: seu_nome", key="log_user")
        login_senha = st.text_input("Senha", type="password", placeholder="••••••••", key="log_pass")
        
        if st.button("Entrar", use_container_width=True, type="primary"):
            if login_user and login_senha:
                # UX: SPINNER DE CARREGAMENTO ADICIONADO AQUI
                with st.spinner("🔄 Conectando aos servidores seguros... isso leva alguns segundos."):
                    dados_usuario = validar_login(login_user, login_senha)
                    if dados_usuario:
                        st.session_state.logged_in = True
                        st.session_state.username = login_user
                        st.session_state.nome_usuario = dados_usuario.get("nome", "Usuário")
                        
                        perfil_carregado = dados_usuario.get("perfil")
                        st.session_state.perfil = perfil_carregado if isinstance(perfil_carregado, dict) else {}
                        st.session_state.despensa = carregar_despensa(login_user)
                        st.rerun()
                    else: st.error("Usuário ou senha incorretos.")
            else: st.warning("Preencha todos os campos.")
                
        st.markdown("<div style='text-align: center; margin: 15px 0; color: #8E8E93;'>ou</div>", unsafe_allow_html=True)
        if GOOGLE_CLIENT_ID: st.markdown(f'<a href="{gerar_url_google()}" class="btn-google-nativo" target="_top">{GOOGLE_SVG} Continuar com Google</a>', unsafe_allow_html=True)

    with st.expander("Criar Conta Nova"):
        cad_nome = st.text_input("Como quer ser chamado?")
        cad_user = st.text_input("Nome de usuário (ex: pablo)").lower()
        cad_senha = st.text_input("Crie uma senha", type="password")
        if st.button("Criar Conta", use_container_width=True):
            if criar_conta(cad_user, cad_nome, cad_senha): st.success("Conta criada! Pode logar.")
            else: st.error("Usuário já existe.")

# ==========================================
# MÓDULO 2: O APLICATIVO (LOGADO) - BLINDADO
# ==========================================
else:
    try:
        perfil_seguro = st.session_state.perfil if isinstance(st.session_state.perfil, dict) else {}
        
        p_idade = safe_int(perfil_seguro.get("idade"), 30)
        p_peso = safe_float(perfil_seguro.get("peso"), 70.0)
        p_altura = safe_int(perfil_seguro.get("altura"), 170)
        p_obj = str(perfil_seguro.get("objetivo") or "Emagrecimento")
        p_atv = str(perfil_seguro.get("atividade") or "Moderada")
        foto_salva = perfil_seguro.get("foto")
        streak_atual = safe_int(perfil_seguro.get("streak"), 1)
        
        eh_pro = str(perfil_seguro.get("plano", "gratis")) == "premium"
        badge_pro = "👑 PRO" if eh_pro else ""

        hoje = datetime.now(fuso_local).date()
        hoje_str = hoje.strftime("%Y-%m-%d")
        ontem = hoje - timedelta(days=1)
        last_login_str = str(perfil_seguro.get("last_login") or "")

        if last_login_str:
            try:
                last_login_date = datetime.strptime(last_login_str, "%Y-%m-%d").date()
                if last_login_date == ontem: streak_atual += 1  
                elif last_login_date < ontem: streak_atual = 1   
            except: pass
        
        if last_login_str != hoje_str:
            st.session_state.perfil["last_login"] = hoje_str
            st.session_state.perfil["streak"] = streak_atual
            salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)

        hora_atual = datetime.now(fuso_local).hour
        if hora_atual < 12: saudacao, icone_tempo = "Bom dia", "☀️"
        elif hora_atual < 18: saudacao, icone_tempo = "Boa tarde", "☕"
        else: saudacao, icone_tempo = "Boa noite", "🌙"

        col_empty, col_title, col_profile = st.columns([1, 2.5, 1], vertical_alignment="center")
        with col_title:
            st.markdown(f"""
                <div style="text-align: center; padding-top: 5px;">
                    <h1 class="adapt-text" style="font-weight: 800; font-size: 2rem; margin-bottom: 0;">NutryAi <span style="font-size: 1rem; color:#FFD700;">{badge_pro}</span></h1>
                    <p style="color: #8E8E93; font-size: 0.9rem; margin-top: -5px;">{saudacao}, {st.session_state.nome_usuario}! <span style="color:#FF9500; font-weight:bold;">🔥 {streak_atual}</span></p>
                </div>
            """, unsafe_allow_html=True)
            
        with col_profile:
            with st.popover("⚙️", use_container_width=True):
                tab_dados, tab_bio = st.tabs(["👤 Dados", "⚖️ Bio"])
                
                with tab_dados:
                    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
                    if foto_salva: st.markdown(f'<img src="data:image/jpeg;base64,{foto_salva}" width="80" height="80" style="border-radius:50%; object-fit:cover; margin-bottom:10px;">', unsafe_allow_html=True)
                    else: st.markdown('<div style="font-size: 40px; margin-bottom: 10px;">👤</div>', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    nova_foto = st.file_uploader("Trocar foto", type=["jpg", "png"])
                    novo_nome = st.text_input("Nome", value=st.session_state.nome_usuario)
                    nova_idade = st.number_input("Idade", value=p_idade)

                with tab_bio:
                    novo_peso = st.number_input("Peso (kg)", value=p_peso, step=0.5)
                    novo_altura = st.number_input("Altura (cm)", value=p_altura)
                    objetivos = ["Emagrecimento", "Hipertrofia", "Manutenção", "Controle Glicêmico"]
                    try: idx_obj = objetivos.index(p_obj)
                    except: idx_obj = 0
                    novo_obj = st.selectbox("Objetivo", objetivos, index=idx_obj)
                    
                    atividades = ["Sedentário", "Leve", "Moderada", "Intensa"]
                    try: idx_atv = atividades.index(p_atv)
                    except: idx_atv = 2
                    nova_atv = st.selectbox("Atividade", atividades, index=idx_atv)
                
                if st.button("💾 Salvar", type="primary", use_container_width=True):
                    if nova_foto:
                        img = Image.open(nova_foto)
                        img.thumbnail((200, 200)) 
                        buffered = BytesIO()
                        img.convert('RGB').save(buffered, format="JPEG")
                        foto_salva = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    
                    st.session_state.perfil.update({"idade": nova_idade, "peso": novo_peso, "altura": nova_altura, "objetivo": novo_obj, "atividade": nova_atv, "foto": foto_salva})
                    st.session_state.nome_usuario = novo_nome
                    salvar_perfil(st.session_state.username, novo_nome, st.session_state.perfil)
                    st.rerun() 
                st.divider()
                if st.button("🚪 Sair", use_container_width=True): fazer_logout()

        dados_perfil_ia = f"{p_idade} anos, {p_peso}kg, {p_altura}cm. Objetivo: {p_obj}. Ativ: {p_atv}."

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🕒", "📦", "🍽️", "📈", "👩‍⚕️ PRO", "💬 PRO"])

        with tab1:
            with st.container(border=True):
                st.subheader("Blocos Ocupados")
                c1, c2 = st.columns(2)
                hora_acordar = c1.time_input("☀️ Acordar", time(6, 30))
                hora_dormir = c2.time_input("🌙 Dormir", time(23, 0))
                c3, c4 = st.columns(2)
                trab_inicio = c3.time_input("💼 Trab.", time(8, 0))
                trab_fim = c4.time_input("Fim", time(17, 30))
                tempo_preparo = st.slider("⏱️ Prep (min)", 0, 120, 30)
                if st.button("Salvar Horários", use_container_width=True, type="primary"):
                    st.session_state.cardapio_atual = None
                    st.session_state.consumidos = set()
                    st.success("✅ Ajustes salvos.")

        with tab2:
            st.markdown("### 🛒 Seu Estoque")
            col_add, col_rem = st.columns(2)
            with col_add:
                with st.popover("➕ Novo", use_container_width=True):
                    novo_nome = st.text_input("Alimento")
                    nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
                    nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un", "dose"])
                    novo_pronto = st.radio("Pronto?", ["Não", "Sim"], horizontal=True)
                    if st.button("Salvar", type="primary") and novo_nome:
                        novo_item = pd.DataFrame({"Alimento": [novo_nome], "Quantidade": [float(nova_qtd)], "Unidade": [nova_unidade], "Pronto/Rápido": [novo_pronto]})
                        if st.session_state.despensa.empty:
                            st.session_state.despensa = novo_item
                        else:
                            st.session_state.despensa = pd.concat([st.session_state.despensa, novo_item], ignore_index=True)
                        salvar_despensa(st.session_state.despensa, st.session_state.username) 
                        st.rerun()
            with col_rem:
                with st.popover("🗑️ Deletar", use_container_width=True):
                    if not st.session_state.despensa.empty:
                        lista_alimentos = st.session_state.despensa["Alimento"].tolist()
                        item_remover = st.selectbox("Apagar:", lista_alimentos)
                        if st.button("Excluir", type="primary"):
                            st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                            salvar_despensa(st.session_state.despensa, st.session_state.username)
                            st.rerun()
                    else: st.write("Estoque vazio.")
            
            df_visual = st.session_state.despensa.copy() if not st.session_state.despensa.empty else pd.DataFrame()
            if not df_visual.empty and 'Quantidade' in df_visual.columns:
                def formatar_estoque(row): 
                    try: qtd = float(row.get("Quantidade", 0))
                    except: qtd = 0
                    return "❌ ESGOTADO" if qtd <= 0 else f"{qtd} {row.get('Unidade', '')}"
                
                df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
                df_visual.set_index("Alimento", inplace=True)
                st.table(df_visual[["Disponível"]])
                
                st.divider()
                qtd_numerica = pd.to_numeric(st.session_state.despensa['Quantidade'], errors='coerce').fillna(0)
                estoque_zerado = st.session_state.despensa[qtd_numerica <= 0]
                
                if not estoque_zerado.empty:
                    st.warning("⚠️ Lista do Mercado:")
                    texto_zap = "🛒 *Lista do Mercado - NutryAi*\n\n"
                    for index, row in estoque_zerado.iterrows(): 
                        st.write(f"- {row['Alimento']}")
                        texto_zap += f"• {row['Alimento']}\n"
                    link_whatsapp = f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto_zap)}"
                    st.markdown(f'<a href="{link_whatsapp}" target="_blank" style="display:block; text-align:center; background:#25D366; color:white; padding:10px; border-radius:10px; text-decoration:none; font-weight:bold; margin-top:10px;">🟢 Compartilhar Zap</a>', unsafe_allow_html=True)
            else:
                st.info("Nenhum alimento cadastrado.")

        with tab3:
            if st.session_state.cardapio_atual is None:
                if st.button("⚡ Gerar Cardápio de Hoje", use_container_width=True, type="primary"):
                    if not api_configurada: st.error("⚠️ Configure a chave de API do Gemini nos Secrets.")
                    else:
                        with st.spinner("Calculando com a IA..."):
                            df_temp = st.session_state.despensa.copy()
                            if not df_temp.empty:
                                df_temp['Quantidade_Num'] = pd.to_numeric(df_temp['Quantidade'], errors='coerce').fillna(0)
                                despensa_ativa = df_temp[df_temp["Quantidade_Num"] > 0]
                            else: despensa_ativa = pd.DataFrame()
                            
                            prompt = f"""
                            Nutricionista Clínico especialista. Crie o cardápio real de hoje usando APENAS O ESTOQUE.
                            BIOMETRIA: {dados_perfil_ia}
                            AGENDA: Acorda {hora_acordar.strftime('%H:%M')} | Trab {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')} | Prep. Máx: {tempo_preparo} min.
                            ESTOQUE: {despensa_ativa.to_dict(orient="records")}
                            Retorne JSON exato: {{"resumo_diario": {{"calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "ingredientes": "Qtd", "instrucao_preparo": "Instrução", "macros": {{"calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g"}}, "uso_despensa": [{{"nome_exato": "NOME", "qtd_descontada": 150}}]}}]}}
                            """
                            try:
                                resp = modelo.generate_content(prompt).text.strip()
                                st.session_state.cardapio_atual = json.loads(re.search(r'\{.*\}', resp, re.DOTALL).group(0))
                                st.rerun()
                            except Exception as e: st.error(f"Erro na IA: {e}")

            if st.session_state.cardapio_atual is not None:
                refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
                st.markdown("### 🗺️ Rota de Hoje")
                for i, ref in enumerate(refeicoes):
                    id_ref = f"ref_{i}"
                    ja_cons = id_ref in st.session_state.consumidos
                    with st.container(border=True):
                        c_txt, c_chk = st.columns([4, 1])
                        with c_txt:
                            st.markdown(f"**{'🟢' if ja_cons else '⚪'} {ref.get('hora','')} | {ref.get('nome','')}**")
                            st.write(f"🍽️ {ref.get('ingredientes','')}")
                        with c_chk:
                            if st.checkbox("Baixa", key=f"c_{i}", value=ja_cons, disabled=ja_cons):
                                st.session_state.consumidos.add(id_ref)
                                for item in ref.get("uso_despensa", []):
                                    if not st.session_state.despensa.empty:
                                        idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == item.get("nome_exato")].tolist()
                                        if idx: 
                                            qtd_atual = float(st.session_state.despensa.at[idx[0], 'Quantidade'])
                                            qtd_descontada = float(item.get("qtd_descontada", 0))
                                            st.session_state.despensa.at[idx[0], 'Quantidade'] = max(0.0, qtd_atual - qtd_descontada)
                                salvar_despensa(st.session_state.despensa, st.session_state.username)
                                st.rerun()

        with tab4:
            st.markdown("### 📈 Sua Evolução")
            historico = perfil_seguro.get("historico_peso", [])
            
            if historico and isinstance(historico, list):
                try:
                    df_hist = pd.DataFrame(historico)
                    df_hist['data'] = pd.to_datetime(df_hist['data'])
                    df_hist = df_hist.set_index('data')
                    st.line_chart(df_hist, y='peso', color="#007AFF")
                except Exception as e: st.write("Erro ao desenhar gráfico.")
            else:
                historico = []
                st.info("Nenhum peso registrado ainda.")
                
            c_peso, c_btn = st.columns([2, 1], vertical_alignment="bottom")
            with c_peso: novo_registro = st.number_input("Peso de Hoje (kg)", value=p_peso, step=0.5)
            with c_btn:
                if st.button("➕ Salvar", use_container_width=True, type="primary"):
                    historico.append({"data": hoje_str, "peso": float(novo_registro)})
                    st.session_state.perfil["historico_peso"] = historico
                    st.session_state.perfil["peso"] = float(novo_registro)
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    st.toast("✅ Peso registrado!")
                    st.rerun()

        with tab5:
            if not eh_pro:
                st.markdown("""
                <div style='text-align: center; padding: 40px 20px; background-color: var(--card-bg); border-radius: 14px; border: 1px solid var(--border-color); margin-top: 10px;'>
                    <h1 style='font-size: 4rem; margin-bottom: 5px;'>👑</h1>
                    <h2 class='adapt-text' style='font-weight: 800;'>Recurso Premium</h2>
                    <p style='color: #8E8E93; margin-bottom: 25px;'>Desbloqueie o Plano Ideal e o Chat ao Vivo com a IA.</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🌟 Assinar NutryAi PRO", use_container_width=True, type="primary"):
                    st.session_state.perfil["plano"] = "premium"
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    st.balloons()
                    st.rerun()
            else:
                st.markdown("### 👩‍⚕️ Plano Padrão Ouro")
                if st.button("✨ Gerar Plano Ideal", use_container_width=True, type="primary"):
                    if not api_configurada: st.error("⚠️ Configure a chave de API.")
                    else:
                        with st.spinner("Calculando o mapa nutricional para o seu biotipo..."):
                            prompt_ideal = f"""
                            Nutricionista especialista. Crie um PLANO DE METAS e ESTRUTURAÇÃO DE PRATOS. IGNORAR ESTOQUE.
                            BIOMETRIA: {dados_perfil_ia}
                            REGRAS: Carbo Complexo SEMPRE com Proteína/Gordura Boa. Nenhuma salada matinal.
                            AGENDA: Acorda {hora_acordar.strftime('%H:%M')} | Trab {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')} | Tempo cozinhar: {tempo_preparo} min.
                            Retorne JSON: {{"metas_diarias": {{"calorias": "2000 kcal", "carboidratos": "150g", "proteinas": "140g", "gorduras": "60g", "fibras": "30g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "alvo_macros": "Carbos: 30g | Prot: 25g", "estrutura_prato": "Regra de porções", "sugestoes_flexiveis": "3 opções", "instrucao_clinica": "Explicação clínica"}}]}}
                            """
                            try:
                                resposta_ideal = modelo.generate_content(prompt_ideal)
                                texto_limpo_ideal = re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL).group(0) if re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL) else resposta_ideal.text.strip()
                                st.session_state.cardapio_ideal = json.loads(texto_limpo_ideal)
                            except Exception as e: st.error(f"🚨 Erro: {e}")
                                
                if st.session_state.cardapio_ideal:
                    metas = st.session_state.cardapio_ideal.get("metas_diarias", {})
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("🔥 Kcal", metas.get("calorias", "0"))
                    c2.metric("🌾 Carb", metas.get("carboidratos", "0g"))
                    c3.metric("🥩 Prot", metas.get("proteinas", "0g"))
                    c4.metric("🥑 Gord", metas.get("gorduras", "0g"))
                    c5.metric("🥦 Fibra", metas.get("fibras", "0g"))
                    st.divider()
                    for ref_ideal in st.session_state.cardapio_ideal.get("refeicoes", []):
                        with st.container(border=True):
                            st.markdown(f"#### ⏰ {ref_ideal.get('hora', '')} - {ref_ideal.get('nome', '')}")
                            st.caption(f"**🎯 Alvo:** {ref_ideal.get('alvo_macros', '')}")
                            st.markdown(f"**🧩 Montagem:** {ref_ideal.get('estrutura_prato', '')}")
                            st.markdown(f"**💡 Opções:** {ref_ideal.get('sugestoes_flexiveis', '')}")
                            st.info(f"👩‍⚕️ **Clínica:** {ref_ideal.get('instrucao_clinica', '')}")

        with tab6:
            if not eh_pro:
                st.warning("🔒 Assine o plano PRO para conversar com a Nutricionista.")
            else:
                st.markdown("### 💬 Chat com a Nutri")
                foto_upload = st.file_uploader("📸 Foto do prato ou rótulo", type=["jpg", "jpeg", "png"])
                for msg in st.session_state.chat_history:
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])
                prompt_chat = st.chat_input("Dúvidas no mercado?")
                if prompt_chat:
                    if not api_configurada: st.error("⚠️ Configure a API.")
                    else:
                        st.session_state.chat_history.append({"role": "user", "content": prompt_chat})
                        with st.chat_message("user"):
                            st.markdown(prompt_chat)
                            if foto_upload: st.image(foto_upload, width=250); st.caption("📷 Foto enviada.")
                        with st.chat_message("assistant"):
                            with st.spinner("A Nutri está digitando..."):
                                try:
                                    conteudo_ia = [f"Você é a NutryAi, Nutricionista Clínica. O paciente tem o seguinte perfil: {dados_perfil_ia}. Seja prestativa, use tom amigável. Avalie impactos na insulina se o paciente perguntar sobre alimentos ou fotos.", prompt_chat]
                                    if foto_upload:
                                        imagem_pil = Image.open(foto_upload)
                                        conteudo_ia.append(imagem_pil)
                                    resposta_chat = modelo.generate_content(conteudo_ia)
                                    st.markdown(resposta_chat.text)
                                    st.session_state.chat_history.append({"role": "assistant", "content": resposta_chat.text})
                                except Exception as e: st.error(f"Erro na resposta: {e}")

    except Exception as general_error:
        st.error("🚨 Encontramos uma inconsistência nos seus dados no banco de dados.")
        st.code(traceback.format_exc())
        if st.button("Tentar recarregar página"): st.rerun()
