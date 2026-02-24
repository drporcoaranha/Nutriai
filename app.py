import streamlit as st
import pandas as pd
import re
import json
import time 
from datetime import datetime, time as dt_time, timezone, timedelta
import google.generativeai as genai
import urllib.parse
import requests
import base64
import hashlib
from io import BytesIO
from PIL import Image
from supabase import create_client, Client
import traceback
import altair as alt

# Tenta carregar o controlador de cookies de forma segura
try:
    from streamlit_cookies_controller import CookieController
    cookies_enabled = True
except ImportError:
    cookies_enabled = False

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered", initial_sidebar_state="collapsed") 
fuso_local = timezone(timedelta(hours=-3))

if cookies_enabled:
    cookie_controller = CookieController()

# --- 2. CONEXÃO COM O SUPABASE E MERCADO PAGO ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("⚠️ Chaves do Supabase não encontradas no st.secrets!")
    st.stop()

MERCADOPAGO_ACCESS_TOKEN = st.secrets.get("MERCADOPAGO_ACCESS_TOKEN", "")
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "admin@nutryai.com").lower() 

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"Erro ao conectar com o Banco de Dados: {e}")
    st.stop()

# --- INTEGRAÇÃO MERCADO PAGO ---
def gerar_checkout_mercadopago(email_usuario):
    if not MERCADOPAGO_ACCESS_TOKEN: return None
    
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "items": [
            {
                "title": "NutryAi PRO - Plano Mensal",
                "description": "Acesso total à Inteligência Artificial Nutricional",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 29.90
            }
        ],
        "payer": {
            "email": email_usuario
        },
        "back_urls": {
            "success": REDIRECT_URI, 
            "failure": REDIRECT_URI,
            "pending": REDIRECT_URI
        },
        "auto_return": "approved",
        "external_reference": email_usuario 
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code in [200, 201]:
            return res.json().get("init_point") 
    except Exception as e: pass
    return None

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

def validar_login(email, senha):
    try:
        res = supabase.table('users').select('*').eq('username', email.lower()).execute()
        if len(res.data) > 0:
            user = res.data[0]
            if user.get('senha') == hash_senha(senha):
                return user
            elif user.get('senha') == hash_senha("google_sso_senha_dummy"):
                return "google_only"
    except Exception as e: pass
    return None

def criar_conta(email, nome, senha):
    try:
        res = supabase.table('users').select('*').eq('username', email.lower()).execute()
        if len(res.data) > 0:
            user = res.data[0]
            if user.get('senha') == hash_senha("google_sso_senha_dummy"):
                supabase.table('users').update({"senha": hash_senha(senha)}).eq('username', email.lower()).execute()
                return True
            return False 
            
        novo_perfil = {"idade": 30, "peso": 70.0, "altura": 170, "objetivo": "Emagrecimento", "atividade": "Moderada", "foto": None, "streak": 1, "last_login": "", "historico_peso": [], "plano": "gratis", "rotina": {}, "rotina_preenchida": False, "onboarding_concluido": False, "agua_diaria": {"data": "", "copos": 0}, "auto_renovar": False}
        supabase.table('users').insert({"username": email.lower(), "nome": nome, "senha": hash_senha(senha), "perfil": novo_perfil}).execute()
        return True
    except Exception as e: return False

def salvar_perfil(username, nome_atualizado, perfil_data):
    try: supabase.table('users').update({"nome": nome_atualizado, "perfil": perfil_data}).eq('username', username).execute()
    except Exception as e: pass

def carregar_despensa(username):
    df_vazio = pd.DataFrame(columns=['Alimento', 'Quantidade', 'Unidade', 'Pronto/Rápido'])
    try:
        res = supabase.table('despensa').select('*').eq('username', username).execute()
        if len(res.data) > 0:
            df = pd.DataFrame(res.data)
            if 'quantidade' in df.columns: df['quantidade'] = pd.to_numeric(df['quantidade'], errors='coerce').fillna(0)
            df = df.rename(columns={"alimento": "Alimento", "quantidade": "Quantidade", "unidade": "Unidade", "pronto_rapido": "Pronto/Rápido"})
            for col in ['Alimento', 'Quantidade', 'Unidade', 'Pronto/Rápido']:
                if col not in df.columns: df[col] = "" if col != 'Quantidade' else 0.0
            return df[['Alimento', 'Quantidade', 'Unidade', 'Pronto/Rápido']]
    except Exception as e: pass
    return df_vazio 

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
    if texto is None: return 0
    numeros = re.findall(r'\d+', str(texto))
    return int(numeros[0]) if numeros else 0

def safe_int(valor, padrao):
    try: return int(valor) if valor is not None else padrao
    except: return padrao

def safe_float(valor, padrao):
    try: return float(valor) if valor is not None else padrao
    except: return padrao

def str_to_time(time_str, default):
    if not time_str: return default
    try: return datetime.strptime(time_str, "%H:%M").time()
    except: return default

# --- 5. VERIFICAÇÃO DE API GEMINI ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        modelos_disponiveis = [m.name for m in genai.list_models() if 'flash' in m.name]
        if "models/gemini-2.5-flash" in modelos_disponiveis: modelo_exato = "models/gemini-2.5-flash"
        elif modelos_disponiveis: modelo_exato = modelos_disponiveis[-1]
        else: modelo_exato = "gemini-pro"
        modelo = genai.GenerativeModel(modelo_exato) 
        api_configurada = True
    except Exception as e: pass

# --- 6. INICIALIZAÇÃO DE SESSÃO LIMPA ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = None
if 'nome_usuario' not in st.session_state: st.session_state.nome_usuario = None
if 'perfil' not in st.session_state: st.session_state.perfil = {}
if 'despensa' not in st.session_state: st.session_state.despensa = pd.DataFrame()
if 'cardapio_atual' not in st.session_state: st.session_state.cardapio_atual = None
if 'cardapio_ideal' not in st.session_state: st.session_state.cardapio_ideal = None
if 'consumidos' not in st.session_state: st.session_state.consumidos = set()
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'sessao_iniciada' not in st.session_state: st.session_state.sessao_iniciada = False
if 'cadastro_sucesso' not in st.session_state: st.session_state.cadastro_sucesso = False

def fazer_logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.query_params.clear() 
    st.rerun()

# --- 7. INTERCEPTADORES E WEBHOOKS BLINDADOS (ANTI-RACE CONDITION) ---
if "status" in st.query_params and "external_reference" in st.query_params:
    status_pagamento = st.query_params.get("status")
    email_pagador = st.query_params.get("external_reference")
    payment_id = st.query_params.get("payment_id")
    
    if st.session_state.get("ultimo_pagamento_id") == payment_id:
        st.query_params.clear()
    elif status_pagamento == "approved" and email_pagador:
        st.session_state["ultimo_pagamento_id"] = payment_id
        ph = st.empty()
        ph.info("🔄 Validando seu pagamento com o Mercado Pago...")
        pagamento_valido = False
        
        if payment_id and MERCADOPAGO_ACCESS_TOKEN:
            try:
                ver_res = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers={"Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}"})
                if ver_res.status_code == 200 and ver_res.json().get("status") == "approved":
                    pagamento_valido = True
            except: pass
        else:
            pagamento_valido = True 

        if pagamento_valido:
            try:
                res_db = supabase.table('users').select('*').eq('username', email_pagador.lower()).execute()
                if len(res_db.data) > 0:
                    perfil_atual = res_db.data[0].get("perfil", {})
                    perfil_atual["plano"] = "premium"
                    perfil_atual["data_assinatura"] = datetime.now(fuso_local).strftime("%Y-%m-%d")
                    perfil_atual["auto_renovar"] = True
                    
                    supabase.table('users').update({"perfil": perfil_atual}).eq('username', email_pagador.lower()).execute()
                    
                    if st.session_state.username == email_pagador.lower():
                        st.session_state.perfil["plano"] = "premium"
                        st.session_state.perfil["data_assinatura"] = perfil_atual["data_assinatura"]
                        st.session_state.perfil["auto_renovar"] = True
                        
                    ph.empty()
                    st.balloons()
                    st.success("🎉 Pagamento Aprovado! Bem-vindo ao NutryAi PRO.")
                    time.sleep(3)
                    
                    st.query_params.clear()
                    st.rerun()
            except Exception as e: 
                ph.error("Erro ao sincronizar pagamento. Contate o suporte.")
                time.sleep(3)
                st.query_params.clear()
                st.rerun()
        else:
            st.query_params.clear()
            st.rerun()

elif not st.session_state.logged_in and "code" in st.query_params:
    codigo_autorizacao = st.query_params["code"]
    
    if st.session_state.get("ultimo_codigo_google") == codigo_autorizacao:
        st.query_params.clear()
    else:
        st.session_state["ultimo_codigo_google"] = codigo_autorizacao
        
        ph_g = st.empty()
        ph_g.info("🔄 Conectando com o Google...")
        
        try:
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {"code": codigo_autorizacao, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"}
            res = requests.post(token_url, data=token_data)
            
            if res.status_code == 200:
                access_token = res.json().get("access_token")
                user_res = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
                
                if user_res.status_code == 200:
                    google_user = user_res.json()
                    username_google = google_user.get("email") 
                    nome_google = google_user.get("given_name", "Usuário") 
                    
                    res_db = supabase.table('users').select('*').eq('username', username_google).execute()
                    if len(res_db.data) == 0:
                        criar_conta(username_google, nome_google, "google_sso_senha_dummy")
                        res_db = supabase.table('users').select('*').eq('username', username_google).execute()
                    
                    user_db = res_db.data[0]
                    st.session_state.logged_in = True
                    st.session_state.username = username_google
                    st.session_state.nome_usuario = user_db.get('nome', 'Usuário')
                    st.session_state.perfil = user_db.get("perfil") if isinstance(user_db.get("perfil"), dict) else {}
                    st.session_state.despensa = carregar_despensa(username_google)
                    
                    ph_g.empty()
                    st.query_params.clear() 
                    st.rerun() 
                else:
                    ph_g.error("Falha ao ler o perfil do Google.")
                    time.sleep(2)
                    st.query_params.clear()
                    st.rerun()
            else:
                ph_g.error("Aguarde, concluindo login...")
                time.sleep(1)
                st.query_params.clear()
                st.rerun()
        except Exception as e: 
            ph_g.error("Falha na conexão com os servidores do Google.")
            time.sleep(2)
            st.query_params.clear()
            st.rerun()

# --- 8. INJEÇÃO DE PWA, MANIFEST E SPLASH SCREEN NATIVO ---
manifest_dict = {
    "name": "NutryAi PRO",
    "short_name": "NutryAi",
    "description": "Sua Inteligência Nutricional",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#F5F5F7",
    "theme_color": "#34C759",
    "icons": [
        {"src": "https://emojicdn.elk.sh/1f34f", "sizes": "192x192", "type": "image/png"},
        {"src": "https://emojicdn.elk.sh/1f34f", "sizes": "512x512", "type": "image/png"}
    ]
}
manifest_json = json.dumps(manifest_dict)
manifest_b64 = base64.b64encode(manifest_json.encode()).decode("utf-8")

splash_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1170 2532" style="background-color:#F5F5F7;"><text x="50%" y="45%" font-size="200" text-anchor="middle" dominant-baseline="middle">🍏</text><text x="50%" y="55%" font-family="-apple-system, sans-serif" font-size="100" font-weight="900" fill="#1C1C1E" text-anchor="middle" dominant-baseline="middle">NutryAi</text></svg>"""
splash_b64 = base64.b64encode(splash_svg.encode()).decode("utf-8")

st.markdown(f"""
    <link rel="manifest" href="data:application/json;base64,{manifest_b64}">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="NutryAi">
    <link rel="apple-touch-icon" href="https://emojicdn.elk.sh/1f34f">
    <link rel="apple-touch-startup-image" media="screen" href="data:image/svg+xml;base64,{splash_b64}">
    
    <style>
    :root {{ --bg-color: #F5F5F7; --card-bg: #FFFFFF; --border-color: #E5E5EA; --input-border: #C7C7CC; --input-bg: #FAFAFA; --text-primary: #1C1C1E; --text-secondary: #8E8E93; --shadow-color: rgba(0, 0, 0, 0.04); --accent-color: #34C759; --accent-gradient: linear-gradient(135deg, #34C759 0%, #32D74B 100%); }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg-color: #000000; --card-bg: #1C1C1E; --border-color: #2C2C2E; --input-border: #48484A; --input-bg: #2C2C2E; --text-primary: #F2F2F7; --text-secondary: #8E8E93; --shadow-color: rgba(0, 0, 0, 0.5); --accent-color: #30D158; --accent-gradient: linear-gradient(135deg, #30D158 0%, #28CD41 100%); }} }}
    
    header {{ visibility: hidden !important; height: 0px !important; display: none !important; }}
    .stAppHeader {{ visibility: hidden !important; height: 0px !important; display: none !important; }}
    [data-testid="stHeader"] {{ visibility: hidden !important; height: 0px !important; display: none !important; }}
    [data-testid="stToolbar"] {{ display: none !important; }}
    [data-testid="stAppDeployButton"] {{ display: none !important; }}
    .stDeployButton {{ display: none !important; }}
    #stDecoration {{ display: none !important; }}
    .viewerBadge_container__1QSob {{ display: none !important; }}
    [data-testid="stSidebar"] {{ display: none !important; }} 
    [data-testid="collapsedControl"] {{ display: none !important; }} 
    #MainMenu {{ display: none !important; }} 
    footer {{ display: none !important; }} 
    
    .block-container {{ padding-top: 1rem !important; padding-bottom: 5rem; max-width: 600px !important; margin: 0 auto !important; }}
    .stApp {{ background-color: var(--bg-color) !important; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", Helvetica, Arial, sans-serif !important; }}
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{ background-color: var(--card-bg) !important; border-radius: 20px !important; border: 1px solid var(--border-color) !important; box-shadow: 0px 8px 24px var(--shadow-color) !important; padding: 20px !important; }}
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {{ border: 1.5px solid var(--input-border) !important; background-color: var(--input-bg) !important; border-radius: 12px !important; }}
    div[data-baseweb="input"] > div:focus-within, div[data-baseweb="select"] > div:focus-within {{ border-color: var(--accent-color) !important; box-shadow: 0 0 0 2px rgba(52,199,89,0.2) !important; }}
    input {{ color: var(--text-primary) !important; font-size: 16px !important; padding: 12px 14px !important; }}
    div[data-testid="stButton"] button, div[data-testid="stPopover"] > button {{ border-radius: 16px !important; height: 50px !important; font-weight: 700 !important; font-size: 16px !important; border: 1px solid var(--input-border) !important; background-color: var(--card-bg) !important; color: var(--text-primary) !important; transition: all 0.15s ease-in-out !important; }}
    div[data-testid="stButton"] button:hover, div[data-testid="stPopover"] > button:hover {{ transform: scale(0.98); opacity: 0.9; }}
    div[data-testid="stButton"] button:active, div[data-testid="stPopover"] > button:active {{ transform: scale(0.92) !important; opacity: 0.7 !important; }}
    div[data-testid="stButton"] button[kind="primary"] {{ background: var(--accent-gradient) !important; color: white !important; border: none !important; }}
    div[data-testid="stTabs"] > div:first-child {{ background-color: var(--bg-color); padding-top: 10px; padding-bottom: 10px; position: -webkit-sticky; position: sticky; top: 0px; z-index: 999; border-bottom: 1px solid var(--border-color); }}
    div[data-testid="stTabs"] button[data-baseweb="tab"] {{ background-color: transparent !important; border-radius: 20px !important; padding: 8px 16px !important; border: none !important; color: var(--text-secondary) !important; }}
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {{ background-color: var(--card-bg) !important; color: var(--text-primary) !important; box-shadow: 0 2px 8px var(--shadow-color) !important; }}
    div[data-testid="stTabs"] button[data-baseweb="tab"] > div[data-testid="stMarkdownContainer"] > p {{ font-size: 1.2rem !important; margin: 0 !important; padding: 0 !important; }}
    .btn-google-nativo {{ display: flex; align-items: center; justify-content: center; background-color: var(--card-bg); color: var(--text-primary); border: 1.5px solid var(--input-border); border-radius: 16px; height: 50px; font-weight: 600; font-size: 16px; text-decoration: none; width: 100%; box-shadow: 0 2px 8px var(--shadow-color); transition: all 0.15s ease; }}
    .btn-pro {{ display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #FFD700 0%, #FF9500 100%); color: #000 !important; border-radius: 16px; height: 55px; font-weight: 800; font-size: 18px; border: none; width: 100%; text-decoration: none; transition: all 0.15s ease; }}
    .btn-whatsapp {{ display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #30D158 0%, #28CD41 100%); color: #FFF !important; border-radius: 16px; height: 50px; font-weight: 700; font-size: 16px; text-decoration: none; width: 100%; margin-top: 15px; transition: all 0.15s ease; }}
    .btn-google-nativo:active, .btn-pro:active, .btn-whatsapp:active {{ transform: scale(0.92) !important; opacity: 0.7 !important; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; background-color: transparent; }} th {{ color: var(--text-secondary) !important; font-weight: 600 !important; border-bottom: 1px solid var(--border-color) !important; text-align: left !important; padding-bottom: 10px !important; }} td, th {{ padding: 14px 8px !important; border-bottom: 1px solid var(--border-color) !important; border-top: none !important; border-left: none !important; border-right: none !important; color: var(--text-primary) !important; }} tr:last-child td {{ border-bottom: none !important; }}
    .macro-bar-container {{ width: 100%; background-color: var(--border-color); border-radius: 10px; height: 8px; margin-top: 6px; overflow: hidden; }} .macro-bar-fill {{ height: 100%; border-radius: 10px; transition: width 0.8s ease; }} .bg-kcal {{ background: linear-gradient(90deg, #FF9500, #FFCC00); }} .bg-prot {{ background: linear-gradient(90deg, #34C759, #32D74B); }} .bg-carb {{ background: linear-gradient(90deg, #007AFF, #5AC8FA); }} .bg-gord {{ background: linear-gradient(90deg, #AF52DE, #FF2D55); }}
    [data-testid="stArrowVegaLiteChart"] {{ pointer-events: none !important; touch-action: none !important; }}
    .adapt-text {{ color: var(--text-primary) !important; }} .sub-text {{ color: var(--text-secondary) !important; font-size: 0.95rem; }}
    .brand-container {{ display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 35px; margin-top: 10px; }} .brand-icon-box {{ background: var(--accent-gradient); width: 70px; height: 70px; border-radius: 20px; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 20px rgba(52, 199, 89, 0.3); margin-bottom: 15px; }} .brand-icon {{ font-size: 38px; line-height: 1; }} .brand-text {{ font-size: 2.8rem; font-weight: 900; margin: 0; padding: 0; line-height: 1.1; background: var(--text-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -1px; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# MÓDULO 1: TELA DE LOGIN & CADASTRO MODAL
# ==========================================
if not st.session_state.logged_in:
    
    @st.dialog("✨ Criar Nova Conta")
    def modal_registo():
        st.markdown("<p style='text-align: center; color: var(--text-secondary); margin-top:-10px; margin-bottom:20px;'>Preencha seus dados para iniciar a jornada.</p>", unsafe_allow_html=True)
        cad_nome = st.text_input("Como quer ser chamado?")
        cad_email = st.text_input("Seu E-mail (será o seu login)").lower()
        cad_senha = st.text_input("Crie uma senha segura", type="password")
        
        st.write("")
        if st.button("Finalizar Cadastro", type="primary", use_container_width=True):
            if cad_nome and cad_email and cad_senha:
                if "@" in cad_email and "." in cad_email:
                    if criar_conta(cad_email, cad_nome, cad_senha):
                        st.session_state.cadastro_sucesso = True
                        st.rerun()
                    else:
                        st.error("⚠️ Este e-mail já está em uso por uma conta. Faça o login.")
                else:
                    st.warning("Por favor, insira um e-mail válido.")
            else:
                st.warning("Preencha todos os campos.")

    @st.dialog("🔒 Recuperação de Senha")
    def modal_esqueci_senha():
        st.write("Para redefinir sua senha de forma segura e imediata, entre em contato com nosso suporte via WhatsApp.")
        st.write("Nossa equipe confirmará sua identidade e criará uma senha temporária na hora!")
        st.link_button("🟢 Falar com Suporte (WhatsApp)", "https://wa.me/5511999999999?text=Olá, esqueci a senha do meu aplicativo NutryAi. Podem me ajudar?", type="primary", use_container_width=True)

    with st.container():
        st.markdown("""
            <div class="brand-container">
                <div class="brand-icon-box"><span class="brand-icon">🍏</span></div>
                <h1 class="brand-text">NutryAi</h1>
                <p class="sub-text" style="margin-top: 8px;">Sua inteligência nutricional.</p>
            </div>
        """, unsafe_allow_html=True)

        if st.session_state.cadastro_sucesso:
            st.success("✅ Conta criada com sucesso! Faça login abaixo para iniciar.")
            st.session_state.cadastro_sucesso = False

        with st.container(border=True):
            st.markdown("<h4 class='adapt-text' style='text-align: center; margin-bottom: 20px; font-weight: 700;'>Acesse sua conta</h4>", unsafe_allow_html=True)
            login_user = st.text_input("E-mail", placeholder="ex: seu@email.com", label_visibility="collapsed").lower()
            login_senha = st.text_input("Senha", type="password", placeholder="Sua senha secreta", label_visibility="collapsed")
            
            st.write("")
            if st.button("Entrar no App", use_container_width=True, type="primary"):
                if login_user and login_senha:
                    with st.spinner("🔄 Conectando aos servidores seguros..."):
                        dados_usuario = validar_login(login_user, login_senha)
                        
                        if dados_usuario == "google_only":
                            st.warning("🔗 Conta Google detectada! Faça login com o botão abaixo ou crie uma senha em 'Criar Nova Conta' para acessar manualmente.")
                        elif dados_usuario:
                            st.session_state.logged_in = True
                            st.session_state.username = login_user
                            st.session_state.nome_usuario = dados_usuario.get("nome", "Usuário")
                            perfil_carregado = dados_usuario.get("perfil")
                            st.session_state.perfil = perfil_carregado if isinstance(perfil_carregado, dict) else {}
                            st.session_state.despensa = carregar_despensa(login_user)
                            st.rerun()
                        else: 
                            st.error("E-mail ou senha incorretos.")
                else: st.warning("Preencha todos os campos.")
                
            if st.button("Esqueci minha senha", use_container_width=True):
                modal_esqueci_senha()
                    
            st.markdown("<div style='text-align: center; margin: 15px 0; color: var(--text-secondary); font-size: 0.9rem; font-weight: 600;'>OU</div>", unsafe_allow_html=True)
            if GOOGLE_CLIENT_ID: st.markdown(f'<a href="{gerar_url_google()}" class="btn-google-nativo" target="_top">{GOOGLE_SVG} Continuar com Google</a>', unsafe_allow_html=True)
            
        st.write("")
        st.markdown("<hr style='margin: 10px 0; opacity: 0.2'>", unsafe_allow_html=True)
        if st.button("Não tem conta? Criar Nova Conta", use_container_width=True):
            modal_registo()

# ==========================================
# MÓDULO 2: O APLICATIVO E ONBOARDING
# ==========================================
else:
    perfil_seguro = st.session_state.perfil if isinstance(st.session_state.perfil, dict) else {}
    
    hoje = datetime.now(fuso_local).date()
    hoje_str = hoje.strftime("%Y-%m-%d")
    
    eh_pro = str(perfil_seguro.get("plano", "gratis")) == "premium"
    eh_admin = (st.session_state.username == ADMIN_EMAIL)
    
    if eh_pro:
        data_ass = perfil_seguro.get("data_assinatura")
        if data_ass:
            try:
                data_ass_dt = datetime.strptime(data_ass, "%Y-%m-%d").date()
                if (hoje - data_ass_dt).days >= 30:
                    if not perfil_seguro.get("auto_renovar", True):
                        st.session_state.perfil["plano"] = "gratis"
                        eh_pro = False
                        salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                        st.warning("⚠️ Seu plano PRO expirou. Faça o upgrade novamente para reativar as funções.")
                    else:
                        st.session_state.perfil["data_assinatura"] = hoje_str
                        salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
            except: pass
            
    # --- 🚨 DADOS GLOBAIS DE BIOMETRIA (O HOTFIX) 🚨 ---
    p_idade = safe_int(perfil_seguro.get("idade"), 30)
    p_peso = safe_float(perfil_seguro.get("peso"), 70.0)
    p_altura = safe_int(perfil_seguro.get("altura"), 170)
    p_obj = str(perfil_seguro.get("objetivo") or "Emagrecimento")
    p_atv = str(perfil_seguro.get("atividade") or "Moderada")
    foto_salva = perfil_seguro.get("foto")
    streak_atual = safe_int(perfil_seguro.get("streak"), 1)
    
    dados_perfil_ia = f"{p_idade} anos, {p_peso}kg, {p_altura}cm. Objetivo: {p_obj}. Ativ: {p_atv}."
    
    onboarding_pronto = perfil_seguro.get("onboarding_concluido", False)
    
    if not onboarding_pronto:
        st.markdown("""
            <div style='text-align: center; padding: 20px 10px;'>
                <h1 style='font-size: 4rem; margin-bottom: 5px;'>🍏</h1>
                <h2 class='adapt-text' style='font-weight: 800;'>Bem-vindo ao NutryAi!</h2>
                <p class='sub-text' style='margin-bottom: 25px;'>Para a Inteligência Artificial criar planos perfeitos para você, precisamos de 4 detalhes rápidos.</p>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container(border=True):
            ob_idade = st.number_input("Sua Idade", min_value=10, max_value=120, value=30)
            ob_peso = st.number_input("Seu Peso (kg)", min_value=30.0, max_value=250.0, value=70.0, step=0.5)
            ob_altura = st.number_input("Sua Altura (cm)", min_value=100, max_value=250, value=170)
            ob_obj = st.selectbox("Seu Objetivo Principal", ["Emagrecimento", "Hipertrofia", "Manutenção", "Controle Glicêmico"])
            ob_atv = st.selectbox("Seu Nível de Atividade", ["Sedentário", "Leve", "Moderada", "Intensa"], index=2)
            
            st.write("")
            if st.button("✨ Começar minha Jornada", type="primary", use_container_width=True):
                st.session_state.perfil.update({
                    "idade": ob_idade, "peso": ob_peso, "altura": ob_altura, 
                    "objetivo": ob_obj, "atividade": ob_atv, "onboarding_concluido": True
                })
                st.session_state.perfil["historico_peso"] = [{"data": hoje_str, "peso": float(ob_peso)}]
                salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                st.balloons()
                time.sleep(1.5)
                st.rerun()
                
    else:
        @st.dialog("⚙️ Configurações da Conta")
        def modal_ajustes():
            p_s = st.session_state.perfil if isinstance(st.session_state.perfil, dict) else {}
            m_idade = safe_int(p_s.get("idade"), 30)
            m_peso = safe_float(p_s.get("peso"), 70.0)
            m_altura = safe_int(p_s.get("altura"), 170)
            m_obj = str(p_s.get("objetivo") or "Emagrecimento")
            m_atv = str(p_s.get("atividade") or "Moderada")
            m_foto = p_s.get("foto")
            m_eh_pro = str(p_s.get("plano", "gratis")) == "premium"
            m_hoje_str = datetime.now(fuso_local).strftime("%Y-%m-%d")

            tab_dados, tab_bio, tab_plan = st.tabs(["👤 Dados", "⚖️ Bio", "💳 Plano"])
            
            with tab_dados:
                st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
                if m_foto: st.markdown(f'<img src="data:image/jpeg;base64,{m_foto}" width="80" height="80" style="border-radius:50%; object-fit:cover; margin-bottom:15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">', unsafe_allow_html=True)
                else: st.markdown('<div style="font-size: 40px; margin-bottom: 15px;">👤</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                nova_foto = st.file_uploader("Mudar foto", type=["jpg", "png"], label_visibility="collapsed")
                novo_nome = st.text_input("Seu Nome", value=st.session_state.nome_usuario)
                nova_idade = st.number_input("Idade", value=m_idade)
                
                st.markdown("<h4 class='adapt-text' style='color: #FF3B30; font-size: 0.9rem; margin-top: 20px; margin-bottom: 5px;'>🚨 Zona de Perigo</h4>", unsafe_allow_html=True)
                with st.expander("Excluir minha conta permanentemente"):
                    st.warning("Esta ação apagará todos os seus dados, histórico e despensa. Não pode ser desfeita.")
                    check_del = st.checkbox("Sim, quero apagar tudo.", key="chk_del_conta")
                    if st.button("🗑️ Confirmar Exclusão", disabled=not check_del, use_container_width=True):
                        with st.spinner("Apagando dados..."):
                            try:
                                supabase.table('despensa').delete().eq('username', st.session_state.username).execute()
                                supabase.table('users').delete().eq('username', st.session_state.username).execute()
                                st.success("Adeus! Conta apagada com sucesso.")
                                time.sleep(1.5)
                                fazer_logout()
                            except Exception as e:
                                st.error("Erro ao apagar. Contate o suporte.")

            with tab_bio:
                novo_peso = st.number_input("Peso (kg)", value=m_peso, step=0.5)
                novo_altura = st.number_input("Altura (cm)", value=m_altura)
                objetivos = ["Emagrecimento", "Hipertrofia", "Manutenção", "Controle Glicêmico"]
                try: idx_obj = objetivos.index(m_obj)
                except: idx_obj = 0
                novo_obj = st.selectbox("Objetivo Principal", objetivos, index=idx_obj)
                atividades = ["Sedentário", "Leve", "Moderada", "Intensa"]
                try: idx_atv = atividades.index(m_atv)
                except: idx_atv = 2
                nova_atv = st.selectbox("Nível de Atividade", atividades, index=idx_atv)
                
            with tab_plan:
                if m_eh_pro:
                    st.markdown("<h4 class='adapt-text' style='margin-top:0;'>👑 NutryAi PRO</h4>", unsafe_allow_html=True)
                    data_ass = p_s.get("data_assinatura", m_hoje_str)
                    try:
                        data_ass_dt = datetime.strptime(data_ass, "%Y-%m-%d").date()
                        vencimento_dt = data_ass_dt + timedelta(days=30)
                        vencimento_str = vencimento_dt.strftime("%d/%m/%Y")
                        dias_restantes = (vencimento_dt - datetime.now(fuso_local).date()).days
                    except:
                        vencimento_str = "Indisponível"
                        dias_restantes = 0
                    
                    auto_renovar = p_s.get("auto_renovar", True)
                    
                    with st.container(border=True):
                        st.write(f"**Vencimento:** {vencimento_str} ({max(0, dias_restantes)} dias)")
                        st.write(f"**Renovação Automática:** {'✅ Ativada' if auto_renovar else '❌ Desativada'}")
                        
                        st.divider()
                        st.link_button("💳 Gerenciar no Mercado Pago", "https://www.mercadopago.com.br/subscriptions", use_container_width=True)
                        
                        st.write("")
                        if auto_renovar:
                            if st.button("🚨 Cancelar Assinatura Interna", use_container_width=True):
                                st.session_state.perfil["auto_renovar"] = False
                                salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                st.rerun()
                        else:
                            if st.button("🔄 Reativar Renovação", type="primary", use_container_width=True):
                                st.session_state.perfil["auto_renovar"] = True
                                salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                st.rerun()
                else:
                    st.markdown("<h4 class='adapt-text' style='margin-top:0;'>🍏 Plano Básico</h4>", unsafe_allow_html=True)
                    st.info("Você está usando a versão gratuita. Suas funções são limitadas.")
                    
                    link_mp = gerar_checkout_mercadopago(st.session_state.username)
                    if link_mp:
                        st.link_button("💳 Assinar NutryAi PRO (R$ 29,90)", url=link_mp, type="primary", use_container_width=True)
                    else:
                        st.error("⚠️ Sistema de pagamentos indisponível.")
                        
                    st.write("")
                    with st.expander("🎁 Tem um Cupom Promocional?"):
                        cod_cupom_ajustes = st.text_input("Código promocional", label_visibility="collapsed", placeholder="Digite seu código...", key="cupom_ajustes_modal")
                        if st.button("Aplicar Cupom", use_container_width=True, key="btn_cupom_ajustes_modal"):
                            if cod_cupom_ajustes.strip().upper() == "GRATIS30": 
                                st.session_state.perfil["plano"] = "premium"
                                st.session_state.perfil["data_assinatura"] = m_hoje_str
                                st.session_state.perfil["auto_renovar"] = False 
                                salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                st.balloons()
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error("Cupom inválido ou expirado.")
                
                st.write("")
                with st.expander("📱 Como Instalar o App no Celular"):
                    st.markdown("""
                    **🍎 iPhone (Safari):**
                    1. Toque no ícone de **Compartilhar** no rodapé.
                    2. Selecione **"Adicionar à Tela de Início"**.
                    3. Confirme em **"Adicionar"**.

                    **🤖 Android (Chrome):**
                    1. Toque nos **3 pontinhos** no topo.
                    2. Selecione **"Adicionar à tela inicial"**.
                    3. Confirme.
                    """)
            
            st.write("")
            c1, c2 = st.columns(2)
            if c1.button("💾 Salvar Perfil", type="primary", use_container_width=True):
                if nova_foto:
                    img = Image.open(nova_foto)
                    img.thumbnail((200, 200)) 
                    buffered = BytesIO()
                    img.convert('RGB').save(buffered, format="JPEG")
                    foto_salva = base64.b64encode(buffered.getvalue()).decode("utf-8")
                else:
                    foto_salva = m_foto
                
                st.session_state.perfil.update({"idade": nova_idade, "peso": novo_peso, "altura": novo_altura, "objetivo": novo_obj, "atividade": nova_atv, "foto": foto_salva})
                st.session_state.nome_usuario = novo_nome
                salvar_perfil(st.session_state.username, novo_nome, st.session_state.perfil)
                st.toast("✅ Perfil atualizado com sucesso!")
                time.sleep(0.5)
                st.rerun() 
            if c2.button("🚪 Sair", use_container_width=True): 
                fazer_logout()

        @st.dialog("➕ Adicionar Alimento")
        def modal_adicionar():
            n_nome = st.text_input("Qual o alimento?")
            n_qtd = st.number_input("Quantidade", min_value=0.1, step=1.0)
            n_unidade = st.selectbox("Unidade de Medida", ["g", "kg", "ml", "L", "un", "dose", "colher"])
            n_pronto = st.radio("Consumo Rápido?", ["Não", "Sim"], horizontal=True)
            if st.button("Salvar no Estoque", type="primary", use_container_width=True):
                if n_nome:
                    nome_fmt = n_nome.strip().capitalize()
                    df = st.session_state.despensa
                    if not df.empty and nome_fmt in df['Alimento'].values:
                        idx = df.index[df['Alimento'] == nome_fmt].tolist()[0]
                        df.at[idx, 'Quantidade'] = float(df.at[idx, 'Quantidade']) + float(n_qtd)
                        df.at[idx, 'Unidade'] = n_unidade
                        df.at[idx, 'Pronto/Rápido'] = n_pronto
                    else:
                        novo_item = pd.DataFrame({"Alimento": [nome_fmt], "Quantidade": [float(n_qtd)], "Unidade": [n_unidade], "Pronto/Rápido": [n_pronto]})
                        if df.empty: st.session_state.despensa = novo_item
                        else: st.session_state.despensa = pd.concat([df, novo_item], ignore_index=True)
                    salvar_despensa(st.session_state.despensa, st.session_state.username) 
                    st.rerun() 
                else:
                    st.warning("Digite o nome do alimento.")

        @st.dialog("🗑️ Remover Alimento")
        def modal_remover():
            if not st.session_state.despensa.empty:
                lista_alimentos = st.session_state.despensa["Alimento"].tolist()
                item_remover = st.selectbox("O que acabou?", lista_alimentos)
                if st.button("Excluir Item", type="primary", use_container_width=True):
                    st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                    salvar_despensa(st.session_state.despensa, st.session_state.username)
                    st.rerun() 
            else: 
                st.write("Seu estoque já está vazio.")

        ontem = hoje - timedelta(days=1)
        last_login_str = str(perfil_seguro.get("last_login") or "")

        if not st.session_state.sessao_iniciada:
            cardapio_banco = perfil_seguro.get("cardapio_salvo", {})
            if cardapio_banco.get("data") == hoje_str:
                st.session_state.cardapio_atual = cardapio_banco.get("plan")
                cons_list = cardapio_banco.get("consumidos", [])
                st.session_state.consumidos = set(cons_list) if isinstance(cons_list, list) else set()
            st.session_state.sessao_iniciada = True

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

        agua_memoria = perfil_seguro.get("agua_diaria", {})
        if agua_memoria.get("data") != hoje_str:
            agua_memoria = {"data": hoje_str, "copos": 0}
            st.session_state.perfil["agua_diaria"] = agua_memoria
            
        copos_atuais = st.session_state.perfil["agua_diaria"].get("copos", 0)
        meta_ml = p_peso * 35
        meta_copos = max(4, int(round(meta_ml / 250)))

        hora_atual = datetime.now(fuso_local).hour
        if hora_atual < 12: saudacao = "Bom dia"
        elif hora_atual < 18: saudacao = "Boa tarde"
        else: saudacao = "Boa noite"

        col_text, col_profile = st.columns([3, 1], vertical_alignment="center")
        with col_text:
            badge_html = "<span style='background: linear-gradient(135deg, #FFD700 0%, #FF9500 100%); color: black; font-size: 10px; font-weight: bold; padding: 2px 8px; border-radius: 10px; margin-left: 8px; vertical-align: middle;'>PRO</span>" if eh_pro else ""
            st.markdown(f"""
                <div style="padding-top: 10px; padding-bottom: 5px;">
                    <h2 class="adapt-text" style="font-weight: 800; font-size: 1.8rem; margin: 0; letter-spacing: -0.5px;">NutryAi{badge_html}</h2>
                    <p class="sub-text" style="margin: 0; font-weight: 500;">{saudacao}, {st.session_state.nome_usuario} <span style="color:#FF9500; font-weight:bold; margin-left: 5px;">🔥 {streak_atual}</span></p>
                </div>
            """, unsafe_allow_html=True)
            
        with col_profile:
            if st.button("⚙️ Ajustes", use_container_width=True):
                modal_ajustes()

        titulos_abas = ["🏠", "🕒", "📦", "🍽️", "💧", "📈", "👑", "💬"]
        if eh_admin: titulos_abas.append("📊 Admin")
        
        abas_criadas = st.tabs(titulos_abas)
        tab_home = abas_criadas[0]
        tab_rotina = abas_criadas[1]
        tab_estoque = abas_criadas[2]
        tab_plano = abas_criadas[3]
        tab_agua = abas_criadas[4]
        tab_grafico = abas_criadas[5]
        tab_pro = abas_criadas[6]
        tab_chat = abas_criadas[7]
        
        if eh_admin: tab_admin = abas_criadas[8]

        with tab_home:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>🏠 Resumo do Dia</h3>", unsafe_allow_html=True)
            
            with st.container(border=True):
                st.markdown("<h4 class='adapt-text' style='margin-bottom: 5px;'>🍽️ Seu Menu</h4>", unsafe_allow_html=True)
                if st.session_state.cardapio_atual:
                    refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
                    total_ref = len(refeicoes) if isinstance(refeicoes, list) else 0
                    comidas = len([r for i, r in enumerate(refeicoes) if f"ref_{i}" in st.session_state.consumidos])
                    
                    if total_ref > 0:
                        pct_menu = comidas / total_ref
                        st.progress(pct_menu)
                        if pct_menu == 1.0:
                            st.success("🎉 Todas as refeições concluídas! Excelente trabalho.")
                        else:
                            st.info(f"Progresso: {comidas} de {total_ref} refeições. Continue firme na aba 🍽️!")
                else:
                    st.write("Vá até a aba de **Plano Alimentar (🍽️)** para gerar seu cardápio personalizado com o que você tem na despensa hoje.")
            
            c_agua, c_streak = st.columns(2)
            with c_agua:
                with st.container(border=True):
                    st.markdown("<h4 style='text-align: center; margin-bottom: 5px; color: var(--text-primary);'>💧 Água</h4>", unsafe_allow_html=True)
                    st.markdown(f"<h2 style='text-align: center; color: #007AFF; margin-top: 0;'>{copos_atuais}<span style='font-size: 1rem; color: var(--text-secondary);'>/{meta_copos}</span></h2>", unsafe_allow_html=True)
                    
            with c_streak:
                with st.container(border=True):
                    st.markdown("<h4 style='text-align: center; margin-bottom: 5px; color: var(--text-primary);'>🔥 Ofensiva</h4>", unsafe_allow_html=True)
                    st.markdown(f"<h2 style='text-align: center; color: #FF9500; margin-top: 0;'>{streak_atual} <span style='font-size: 1rem; color: var(--text-secondary);'>dias</span></h2>", unsafe_allow_html=True)

            dicas = [
                "Beba um copo de água logo ao acordar para despertar seu metabolismo.",
                "As fibras ajudam na saciedade. Inclua aveia ou frutas com casca nos lanches!",
                "O sono é crucial. Tente dormir 7 a 8 horas para regular os hormônios da fome.",
                "Mastigue devagar! O cérebro leva cerca de 20 minutos para perceber que está satisfeito.",
                "Evite telas 1 hora antes de dormir para melhorar a regulação da insulina no dia seguinte.",
                "Proteína em todas as refeições ajuda a manter a massa magra e controla a glicemia.",
                "Caminhar 10 a 15 minutos após as grandes refeições reduz os picos de açúcar no sangue."
            ]
            dia_ano = datetime.now(fuso_local).timetuple().tm_yday
            dica_hoje = dicas[dia_ano % len(dicas)]
            
            with st.container(border=True):
                st.markdown("<h4 class='adapt-text'>💡 Dica da Nutri</h4>", unsafe_allow_html=True)
                st.write(f"*{dica_hoje}*")

        with tab_rotina:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>🕒 Sua Rotina</h3>", unsafe_allow_html=True)
            
            rotina_salva = st.session_state.perfil.get("rotina", {})
            tempo_prep_salvo = safe_int(st.session_state.perfil.get("tempo_preparo"), 30)

            with st.container(border=True):
                c1, c2 = st.columns(2)
                hora_acordar = c1.time_input("☀️ Acordar", str_to_time(rotina_salva.get("acordar"), dt_time(6, 30)))
                hora_dormir = c2.time_input("🌙 Dormir", str_to_time(rotina_salva.get("dormir"), dt_time(23, 0)))
                c3, c4 = st.columns(2)
                trab_inicio = c3.time_input("💼 Trab. Início", str_to_time(rotina_salva.get("trab_inicio"), dt_time(8, 0)))
                trab_fim = c4.time_input("💼 Trab. Fim", str_to_time(rotina_salva.get("trab_fim"), dt_time(17, 30)))
                c5, c6 = st.columns(2)
                transito_inicio = c5.time_input("🚗 Trâns. Início", str_to_time(rotina_salva.get("trans_inicio"), dt_time(17, 30)))
                transito_fim = c6.time_input("🏁 Trâns. Fim", str_to_time(rotina_salva.get("trans_fim"), dt_time(18, 30)))
                c7, c8 = st.columns(2)
                treino_inicio = c7.time_input("💪 Treino Início", str_to_time(rotina_salva.get("treino_inicio"), dt_time(19, 0)))
                treino_fim = c8.time_input("🚿 Treino Fim", str_to_time(rotina_salva.get("treino_fim"), dt_time(20, 0)))
                c9, c10 = st.columns(2)
                estudo_inicio = c9.time_input("📚 Estudo Início", str_to_time(rotina_salva.get("estudo_inicio"), dt_time(20, 30)))
                estudo_fim = c10.time_input("📝 Estudo Fim", str_to_time(rotina_salva.get("estudo_fim"), dt_time(22, 0)))
                st.divider()
                tempo_preparo = st.slider("⏱️ Tempo livre para cozinhar (min/dia)", 0, 120, tempo_prep_salvo)
                
                if st.button("Salvar Rotina", use_container_width=True, type="primary"):
                    st.session_state.perfil["rotina"] = {
                        "acordar": hora_acordar.strftime("%H:%M"), "dormir": hora_dormir.strftime("%H:%M"),
                        "trab_inicio": trab_inicio.strftime("%H:%M"), "trab_fim": trab_fim.strftime("%H:%M"),
                        "trans_inicio": transito_inicio.strftime("%H:%M"), "trans_fim": transito_fim.strftime("%H:%M"),
                        "treino_inicio": treino_inicio.strftime("%H:%M"), "treino_fim": treino_fim.strftime("%H:%M"),
                        "estudo_inicio": estudo_inicio.strftime("%H:%M"), "estudo_fim": estudo_fim.strftime("%H:%M")
                    }
                    st.session_state.perfil["tempo_preparo"] = tempo_preparo
                    st.session_state.perfil["rotina_preenchida"] = True
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    
                    st.session_state.cardapio_atual = None
                    st.session_state.consumidos = set()
                    st.toast("✅ Horários salvos no banco de dados!")
                    time.sleep(0.5)
                    st.rerun()

        with tab_estoque:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>📦 Estoque & Mercado</h3>", unsafe_allow_html=True)
            col_add, col_rem = st.columns(2)
            with col_add:
                if st.button("➕ Adicionar", use_container_width=True): modal_adicionar()
            with col_rem:
                if st.button("🗑️ Remover", use_container_width=True): modal_remover()
            
            st.write("")
            with st.container(border=True):
                df_visual = st.session_state.despensa.copy() if not st.session_state.despensa.empty else pd.DataFrame()
                if not df_visual.empty and 'Quantidade' in df_visual.columns:
                    def formatar_estoque(row): 
                        try: qtd = float(row.get("Quantidade", 0))
                        except: qtd = 0
                        return "❌ Faltando" if qtd <= 0 else f"{qtd} {row.get('Unidade', '')}"
                    df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
                    df_visual.set_index("Alimento", inplace=True)
                    st.table(df_visual[["Disponível"]])
                else:
                    st.info("Sua geladeira está vazia no aplicativo.")
                
            st.write("")
            st.markdown("<h4 class='adapt-text' style='font-weight: 700;'>📝 Lista Inteligente</h4>", unsafe_allow_html=True)
            if not st.session_state.despensa.empty and 'Quantidade' in st.session_state.despensa.columns:
                qtd_numerica = pd.to_numeric(st.session_state.despensa['Quantidade'], errors='coerce').fillna(0)
                estoque_zerado = st.session_state.despensa[qtd_numerica <= 0]
                
                if not estoque_zerado.empty:
                    texto_zap = "🛒 *Lista do Mercado - NutryAi*\n\n"
                    for index, row in estoque_zerado.iterrows(): 
                        st.markdown(f"<span style='color: var(--text-primary); font-weight: 600;'>• {row['Alimento']}</span>", unsafe_allow_html=True)
                        texto_zap += f"• {row['Alimento']}\n"
                    link_whatsapp = f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto_zap)}"
                    st.markdown(f'<a href="{link_whatsapp}" target="_blank" class="btn-whatsapp">🟢 Enviar Lista para o Zap</a>', unsafe_allow_html=True)
                else:
                    st.success("🎉 Tudo abastecido! Não falta nada no seu estoque.")

        with tab_plano:
            if st.session_state.cardapio_atual is not None:
                c1, c2 = st.columns([2.5, 1], vertical_alignment="center")
                c1.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 0;'>🍽️ Plano IA</h3>", unsafe_allow_html=True)
                if c2.button("🗑️ Limpar Tudo", use_container_width=True):
                    st.session_state.cardapio_atual = None
                    st.session_state.consumidos = set()
                    if "cardapio_salvo" in st.session_state.perfil:
                        st.session_state.perfil["cardapio_salvo"] = {}
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    st.rerun()
                st.write("")
            else:
                st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>🍽️ Plano Alimentar IA</h3>", unsafe_allow_html=True)
            
            tem_rotina = st.session_state.perfil.get("rotina_preenchida", False)
            df_temp_check = st.session_state.despensa.copy()
            if not df_temp_check.empty:
                df_temp_check['Quantidade_Num'] = pd.to_numeric(df_temp_check['Quantidade'], errors='coerce').fillna(0)
                tem_estoque = not df_temp_check[df_temp_check["Quantidade_Num"] > 0].empty
            else:
                tem_estoque = False

            if st.session_state.cardapio_atual is None:
                if tem_rotina and tem_estoque:
                    st.markdown("""
                    <div style='text-align: center; padding: 40px 20px;'>
                        <h1 style='font-size: 4rem; margin-bottom: 5px; opacity: 0.8;'>🥗</h1>
                        <h3 class='adapt-text' style='font-weight: 700; margin-bottom: 5px;'>Tudo pronto!</h3>
                        <p class='sub-text' style='margin-bottom: 25px;'>Sua rotina e sua despensa estão configuradas. Vamos criar o plano de hoje?</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("⚡ Gerar Plano Alimentar IA", use_container_width=True, type="primary"):
                        if not api_configurada: 
                            st.error("⚠️ Inteligência Artificial offline.")
                        else:
                            with st.spinner("Analisando sua rotina e despensa..."):
                                df_temp = st.session_state.despensa.copy()
                                df_temp['Quantidade_Num'] = pd.to_numeric(df_temp['Quantidade'], errors='coerce').fillna(0)
                                despensa_ativa = df_temp[df_temp["Quantidade_Num"] > 0]
                                rot = st.session_state.perfil.get("rotina", {})
                                t_prep = st.session_state.perfil.get("tempo_preparo", 30)
                                
                                prompt = f"""
                                Nutricionista Clínico. Crie o cardápio real de hoje usando APENAS O ESTOQUE.
                                CULTURA: Culinária típica brasileira. PROIBIDO salada, folhas ou espinafre no café da manhã.
                                BIOMETRIA: {dados_perfil_ia}
                                AGENDA: Acorda {rot.get('acordar','06:30')} | Trab {rot.get('trab_inicio','08:00')}-{rot.get('trab_fim','17:30')} | Transito {rot.get('trans_inicio','17:30')}-{rot.get('trans_fim','18:30')} | Treino {rot.get('treino_inicio','19:00')}-{rot.get('treino_fim','20:00')} | Estudo {rot.get('estudo_inicio','20:30')}-{rot.get('estudo_fim','22:00')} | Dorme {rot.get('dormir','23:00')} | Prep. Máx: {t_prep} min.
                                ESTOQUE: {despensa_ativa.to_dict(orient="records")}
                                Retorne JSON exato: {{"resumo_diario": {{"calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "ingredientes": "Qtd", "instrucao_preparo": "Instrução", "macros": {{"calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g"}}, "uso_despensa": [{{"nome_exato": "NOME", "qtd_descontada": 150}}]}}]}}
                                """
                                try:
                                    resp = modelo.generate_content(prompt).text.strip()
                                    plano_json = json.loads(re.search(r'\{.*\}', resp, re.DOTALL).group(0))
                                    st.session_state.cardapio_atual = plano_json
                                    
                                    st.session_state.perfil["cardapio_salvo"] = {
                                        "data": hoje_str,
                                        "plan": plano_json,
                                        "consumidos": list(st.session_state.consumidos)
                                    }
                                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                    st.rerun()
                                except Exception as e: st.error("A IA gerou um plano vazio ou num formato irreconhecível. Tente clicar em Gerar novamente.")
                else:
                    st.warning("✨ Falta pouco para a Inteligência Artificial assumir o controle!")
                    if not tem_rotina:
                        with st.container(border=True):
                            st.markdown("<h4 class='adapt-text'>🕒 1. Que horas o seu dia começa?</h4>", unsafe_allow_html=True)
                            st.write("A IA precisa conhecer sua rotina para encaixar os lanches nos melhores momentos.")
                            if st.button("Usar Horários Padrões", use_container_width=True):
                                st.session_state.perfil["rotina"] = {"acordar": "07:00", "dormir": "23:00", "trab_inicio": "08:00", "trab_fim": "18:00", "trans_inicio": "18:00", "trans_fim": "19:00", "treino_inicio": "19:00", "treino_fim": "20:00", "estudo_inicio": "20:30", "estudo_fim": "22:00"}
                                st.session_state.perfil["tempo_preparo"] = 30
                                st.session_state.perfil["rotina_preenchida"] = True
                                salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                st.rerun()
                                
                    if not tem_estoque:
                        with st.container(border=True):
                            st.markdown("<h4 class='adapt-text'>✨ 2. Sua despensa parece estar vazia!</h4>", unsafe_allow_html=True)
                            st.write("Para que a IA crie um cardápio perfeito e sem desperdícios, adicione o que tem na geladeira agora:")
                            n_nome = st.text_input("🛒 O que tem na geladeira?", key="fast_alimento", placeholder="Ex: Ovos, Frango, Aveia...")
                            n_qtd = st.number_input("Quantidade", min_value=1.0, step=1.0, key="fast_qtd")
                            if st.button("➕ Salvar na Despensa", type="primary", use_container_width=True):
                                if n_nome:
                                    nome_fmt = n_nome.strip().capitalize()
                                    df = st.session_state.despensa
                                    if not df.empty and nome_fmt in df['Alimento'].values:
                                        idx = df.index[df['Alimento'] == nome_fmt].tolist()[0]
                                        df.at[idx, 'Quantidade'] = float(df.at[idx, 'Quantidade']) + float(n_qtd)
                                    else:
                                        novo_item = pd.DataFrame({"Alimento": [nome_fmt], "Quantidade": [float(n_qtd)], "Unidade": ["g"], "Pronto/Rápido": ["Não"]})
                                        if df.empty: st.session_state.despensa = novo_item
                                        else: st.session_state.despensa = pd.concat([df, novo_item], ignore_index=True)
                                    salvar_despensa(st.session_state.despensa, st.session_state.username) 
                                    st.rerun()

            if st.session_state.cardapio_atual is not None:
                try:
                    resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
                    refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
                    
                    tot_kcal = extrair_numero(resumo.get('calorias_totais', 0)) if isinstance(resumo, dict) else 0
                    tot_prot = extrair_numero(resumo.get('proteinas_totais', 0)) if isinstance(resumo, dict) else 0
                    tot_carb = extrair_numero(resumo.get('carbos_totais', 0)) if isinstance(resumo, dict) else 0
                    tot_gord = extrair_numero(resumo.get('gorduras_totais', 0)) if isinstance(resumo, dict) else 0
                    
                    cons_kcal = cons_prot = cons_carb = cons_gord = 0
                    
                    if not isinstance(st.session_state.consumidos, set):
                        st.session_state.consumidos = set()

                    if isinstance(refeicoes, list):
                        for i, ref in enumerate(refeicoes):
                            if not isinstance(ref, dict): continue
                            if f"ref_{i}" in st.session_state.consumidos:
                                macros = ref.get('macros', {})
                                if isinstance(macros, dict):
                                    cons_kcal += extrair_numero(macros.get('calorias', 0))
                                    cons_prot += extrair_numero(macros.get('proteinas', 0))
                                    cons_carb += extrair_numero(macros.get('carbos', 0))
                                    cons_gord += extrair_numero(macros.get('gorduras', 0))
                                
                    pct_kcal = min(100, int((cons_kcal / tot_kcal * 100) if tot_kcal > 0 else 0))
                    pct_prot = min(100, int((cons_prot / tot_prot * 100) if tot_prot > 0 else 0))
                    pct_carb = min(100, int((cons_carb / tot_carb * 100) if tot_carb > 0 else 0))
                    pct_gord = min(100, int((cons_gord / tot_gord * 100) if tot_gord > 0 else 0))

                    with st.container(border=True):
                        st.markdown("<h4 class='adapt-text' style='font-weight: 700; font-size: 1rem;'>🎯 Meta Diária</h4>", unsafe_allow_html=True)
                        c1, c2, c3, c4 = st.columns(4)
                        c1.markdown(f"<span style='font-size: 0.9rem; font-weight: 600; color: var(--text-primary);'>🔥 Kcal</span><br><span style='font-size: 0.8rem; color: var(--text-secondary);'>{cons_kcal}/{tot_kcal}</span><div class='macro-bar-container'><div class='macro-bar-fill bg-kcal' style='width: {pct_kcal}%;'></div></div>", unsafe_allow_html=True)
                        c2.markdown(f"<span style='font-size: 0.9rem; font-weight: 600; color: var(--text-primary);'>🥩 Prot</span><br><span style='font-size: 0.8rem; color: var(--text-secondary);'>{cons_prot}/{tot_prot}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-prot' style='width: {pct_prot}%;'></div></div>", unsafe_allow_html=True)
                        c3.markdown(f"<span style='font-size: 0.9rem; font-weight: 600; color: var(--text-primary);'>🌾 Carb</span><br><span style='font-size: 0.8rem; color: var(--text-secondary);'>{cons_carb}/{tot_carb}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-carb' style='width: {pct_carb}%;'></div></div>", unsafe_allow_html=True)
                        c4.markdown(f"<span style='font-size: 0.9rem; font-weight: 600; color: var(--text-primary);'>🥑 Gord</span><br><span style='font-size: 0.8rem; color: var(--text-secondary);'>{cons_gord}/{tot_gord}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-gord' style='width: {pct_gord}%;'></div></div>", unsafe_allow_html=True)

                    st.write("")
                    if isinstance(refeicoes, list):
                        texto_exportacao = "🍽️ *Meu Plano NutryAi de Hoje*\n\n"
                        
                        for i, ref in enumerate(refeicoes):
                            if not isinstance(ref, dict): continue
                            
                            hora_ref = ref.get('hora', '')
                            nome_ref = ref.get('nome', '')
                            ingred_ref = ref.get('ingredientes', '')
                            texto_exportacao += f"⏰ *{hora_ref} - {nome_ref}*\n🥑 {ingred_ref}\n\n"
                            
                            id_ref = f"ref_{i}"
                            ja_cons = id_ref in st.session_state.consumidos
                            with st.container(border=True):
                                c_txt, c_chk = st.columns([4, 1], vertical_alignment="center")
                                with c_txt:
                                    cor_bolinha = "🟢" if ja_cons else "⚪"
                                    st.markdown(f"<span style='font-weight: 700; font-size: 1.1rem; color: var(--text-primary);'>{cor_bolinha} {hora_ref} • {nome_ref}</span>", unsafe_allow_html=True)
                                    st.markdown(f"<p style='color: var(--text-primary); margin: 5px 0 0 0;'>🍽️ {ingred_ref}</p>", unsafe_allow_html=True)
                                with c_chk:
                                    foi_marcado = st.checkbox("Baixa", key=f"chk_meal_{i}_{hoje_str}", value=ja_cons, disabled=ja_cons, label_visibility="collapsed")
                                    
                                    if foi_marcado and not ja_cons:
                                        st.session_state.consumidos.add(id_ref)
                                        
                                        if "cardapio_salvo" not in st.session_state.perfil or not isinstance(st.session_state.perfil["cardapio_salvo"], dict):
                                            st.session_state.perfil["cardapio_salvo"] = {}
                                            
                                        st.session_state.perfil["cardapio_salvo"]["consumidos"] = list(st.session_state.consumidos)
                                        salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                                        
                                        try:
                                            uso = ref.get("uso_despensa", [])
                                            if isinstance(uso, list):
                                                for item in uso:
                                                    if isinstance(item, dict):
                                                        nome_alimento = item.get("nome_exato")
                                                        if not st.session_state.despensa.empty and nome_alimento in st.session_state.despensa['Alimento'].values:
                                                            idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == nome_alimento].tolist()[0]
                                                            qtd_atual = float(st.session_state.despensa.at[idx, 'Quantidade'])
                                                            qtd_des = float(item.get("qtd_descontada", 0))
                                                            st.session_state.despensa.at[idx, 'Quantidade'] = max(0.0, qtd_atual - qtd_des)
                                                salvar_despensa(st.session_state.despensa, st.session_state.username)
                                        except Exception: pass
                                        st.rerun()

                        st.write("")
                        link_zap_plano = f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto_exportacao)}"
                        st.markdown(f'<a href="{link_zap_plano}" target="_blank" class="btn-whatsapp" style="margin-bottom: 10px;">🟢 Enviar Plano para o WhatsApp</a>', unsafe_allow_html=True)

                except Exception as e:
                    st.error("A Inteligência Artificial estruturou mal o seu cardápio. Clique em 'Limpar Tudo' no topo da página para recriar.")

        with tab_agua:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>💧 Hidratação Diária</h3>", unsafe_allow_html=True)
            
            pct_agua = min(copos_atuais / meta_copos, 1.0) if meta_copos > 0 else 0
            dash_array = 283 
            dash_offset = dash_array - (dash_array * pct_agua)
            cor_anel = "#32D74B" if pct_agua >= 1.0 else "#007AFF" 
            
            st.markdown(f"""
            <div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
                <svg width="200" height="200" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="45" fill="none" stroke="var(--border-color)" stroke-width="8" />
                    <circle cx="50" cy="50" r="45" fill="none" stroke="{cor_anel}" stroke-width="8" 
                            stroke-dasharray="{dash_array}" stroke-dashoffset="{dash_offset}" 
                            stroke-linecap="round" transform="rotate(-90 50 50)" 
                            style="transition: stroke-dashoffset 0.8s ease-in-out, stroke 0.8s ease;" />
                    <text x="50" y="45" font-family="sans-serif" font-size="22" font-weight="800" fill="var(--text-primary)" text-anchor="middle" dominant-baseline="middle">{copos_atuais}</text>
                    <text x="50" y="65" font-family="sans-serif" font-size="10" font-weight="600" fill="var(--text-secondary)" text-anchor="middle" dominant-baseline="middle">/ {meta_copos} copos</text>
                </svg>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"<p style='text-align:center; color: var(--text-secondary); margin-top:-10px; margin-bottom: 20px;'>Sua meta ideal: <b>{int(meta_ml)}ml</b> (copos de 250ml)</p>", unsafe_allow_html=True)
            
            col_menos, col_vazio, col_mais = st.columns([1, 1, 1])
            with col_menos:
                if st.button("➖ Copo", use_container_width=True):
                    st.session_state.perfil["agua_diaria"]["copos"] = max(0, copos_atuais - 1)
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    st.rerun()
            with col_mais:
                if st.button("➕ Copo", use_container_width=True, type="primary"):
                    st.session_state.perfil["agua_diaria"]["copos"] = copos_atuais + 1
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    if st.session_state.perfil["agua_diaria"]["copos"] == meta_copos:
                        st.balloons() 
                    st.rerun()

        with tab_grafico:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>📈 Gráfico de Evolução</h3>", unsafe_allow_html=True)
            historico = perfil_seguro.get("historico_peso", [])
            
            with st.container(border=True):
                if historico and isinstance(historico, list) and len(historico) > 0:
                    try:
                        df_hist = pd.DataFrame(historico)
                        df_hist['data'] = pd.to_datetime(df_hist['data'])
                        
                        chart = alt.Chart(df_hist).mark_line(
                            point=alt.OverlayMarkDef(filled=True, size=100, color="#34C759"),
                            color="#34C759",
                            strokeWidth=4
                        ).encode(
                            x=alt.X('data:T', axis=alt.Axis(title='', grid=False, format='%d/%m')),
                            y=alt.Y('peso:Q', scale=alt.Scale(zero=False, padding=1), axis=alt.Axis(title='Peso (kg)', grid=True, tickCount=5)),
                            tooltip=[alt.Tooltip('data:T', title='Data', format='%d/%m/%Y'), alt.Tooltip('peso:Q', title='Peso')]
                        ).properties(height=280)
                        
                        st.altair_chart(chart, use_container_width=True)
                    except Exception as e: 
                        st.write("Erro ao desenhar gráfico.")
                else:
                    st.info("O seu gráfico aparecerá aqui após o primeiro registro de peso.")
                
            st.write("")
            c_peso, c_btn = st.columns([2, 1], vertical_alignment="bottom")
            with c_peso: novo_registro = st.number_input("Peso de Hoje (kg)", value=p_peso, step=0.5)
            with c_btn:
                if st.button("➕ Salvar", use_container_width=True, type="primary"):
                    historico.append({"data": hoje_str, "peso": float(novo_registro)})
                    st.session_state.perfil["historico_peso"] = historico
                    st.session_state.perfil["peso"] = float(novo_registro)
                    salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                    st.toast("✅ Peso registrado com sucesso!")
                    time.sleep(0.5)
                    st.rerun()

        with tab_pro:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>👑 NutryAi PRO</h3>", unsafe_allow_html=True)
            if not eh_pro:
                st.markdown("""
                <div style='text-align: center; padding: 40px 20px;'>
                    <h1 style='font-size: 4rem; margin-bottom: 10px;'>🌟</h1>
                    <h2 class='adapt-text' style='font-weight: 800;'>Eleve os seus resultados</h2>
                    <p class='sub-text' style='margin-bottom: 25px;'>Desbloqueie o Plano Padrão Ouro guiado por IA e o Chat ao Vivo com a nossa nutricionista virtual.</p>
                </div>
                """, unsafe_allow_html=True)
                
                link_mp_pro = gerar_checkout_mercadopago(st.session_state.username)
                if link_mp_pro:
                    st.link_button("💳 Assinar agora por R$ 29,90/mês", url=link_mp_pro, type="primary", use_container_width=True)
                    st.caption("Pagamento seguro processado pelo Mercado Pago (Pix e Cartão).")
                else:
                    st.error("⚠️ Sistema de pagamentos indisponível no momento. Contate o suporte.")
                    
                st.write("")
                with st.expander("🎁 Tenho um Cupom Promocional"):
                    cupom_pro = st.text_input("Digite seu código", key="cupom_tab_pro")
                    if st.button("Resgatar Acesso"):
                        if cupom_pro.strip().upper() == "GRATIS30":
                            st.session_state.perfil["plano"] = "premium"
                            st.session_state.perfil["data_assinatura"] = hoje_str
                            st.session_state.perfil["auto_renovar"] = False
                            salvar_perfil(st.session_state.username, st.session_state.nome_usuario, st.session_state.perfil)
                            st.balloons()
                            st.success("Bem-vindo ao NutryAi PRO!")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Código incorreto ou expirado.")
            else:
                if st.button("✨ Gerar Plano Padrão Ouro", use_container_width=True, type="primary"):
                    if not api_configurada: st.error("⚠️ Configure a chave de API.")
                    else:
                        with st.spinner("Mapeando seu biotipo de forma clínica..."):
                            prompt_ideal = f"""
                            Nutricionista especialista. Crie um PLANO DE METAS e ESTRUTURAÇÃO DE PRATOS. IGNORAR ESTOQUE.
                            CULTURA: Culinária típica brasileira. PROIBIDO salada, folhas ou espinafre no café da manhã.
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
                    st.write("")
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("🔥 Kcal", metas.get("calorias", "0"))
                        c2.metric("🌾 Carb", metas.get("carboidratos", "0g"))
                        c3.metric("🥩 Prot", metas.get("proteinas", "0g"))
                        c4.metric("🥑 Gord", metas.get("gorduras", "0g"))
                        c5.metric("🥦 Fibra", metas.get("fibras", "0g"))
                        
                    for ref_ideal in st.session_state.cardapio_ideal.get("refeicoes", []):
                        st.write("")
                        with st.container(border=True):
                            st.markdown(f"<h4 class='adapt-text'>⏰ {ref_ideal.get('hora', '')} • {ref_ideal.get('nome', '')}</h4>", unsafe_allow_html=True)
                            st.caption(f"**🎯 Alvo:** {ref_ideal.get('alvo_macros', '')}")
                            st.markdown(f"**🧩 Montagem:** {ref_ideal.get('estrutura_prato', '')}")
                            st.markdown(f"**💡 Opções:** {ref_ideal.get('sugestoes_flexiveis', '')}")
                            st.info(f"👩‍⚕️ **Clínica:** {ref_ideal.get('instrucao_clinica', '')}")

        with tab_chat:
            st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>💬 Fale com a Nutri</h3>", unsafe_allow_html=True)
            if not eh_pro:
                st.warning("🔒 Assine o plano PRO para conversar com a Inteligência Artificial ao vivo.")
            else:
                with st.container(border=True):
                    foto_upload = st.file_uploader("Dúvidas no restaurante a quilo? Envie a foto do seu prato:", type=["jpg", "jpeg", "png"])
                    
                st.write("")
                for msg in st.session_state.chat_history:
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
                prompt_chat = st.chat_input("Pergunte algo para a IA...")
                if prompt_chat:
                    if not api_configurada: st.error("⚠️ IA Indisponível no momento.")
                    else:
                        st.session_state.chat_history.append({"role": "user", "content": prompt_chat})
                        with st.chat_message("user"):
                            st.markdown(prompt_chat)
                            if foto_upload: st.image(foto_upload, width=250)
                        with st.chat_message("assistant"):
                            with st.spinner("A Nutri está digitando..."):
                                try:
                                    conteudo_ia = [f"Você é a NutryAi, Nutricionista Clínica brasileira. O paciente tem o seguinte perfil: {dados_perfil_ia}. Avalie impactos na insulina se o paciente perguntar sobre alimentos ou fotos.", prompt_chat]
                                    if foto_upload:
                                        imagem_pil = Image.open(foto_upload)
                                        conteudo_ia.append(imagem_pil)
                                    resposta_chat = modelo.generate_content(conteudo_ia)
                                    st.markdown(resposta_chat.text)
                                    st.session_state.chat_history.append({"role": "assistant", "content": resposta_chat.text})
                                except Exception as e: st.error(f"Erro na resposta: {e}")

        # 🚨 PAINEL DO FUNDADOR (ADMIN) 🚨
        if eh_admin:
            with tab_admin:
                st.markdown("<h3 class='adapt-text' style='font-weight: 700; margin-bottom: 20px;'>📊 Painel de Controle (Admin)</h3>", unsafe_allow_html=True)
                try:
                    res_all = supabase.table('users').select('*').execute()
                    users_data = res_all.data
                    
                    if users_data:
                        total_users = len(users_data)
                        premium_users = sum(1 for u in users_data if u.get('perfil', {}).get('plano') == 'premium')
                        
                        c_tot, c_pro = st.columns(2)
                        with c_tot:
                            st.info(f"**Total de Usuários:**\n# {total_users}")
                        with c_pro:
                            st.success(f"**Assinantes PRO:**\n# {premium_users}")
                        
                        st.markdown("#### Lista de Usuários")
                        lista_limpa = []
                        for u in users_data:
                            p = u.get('perfil', {})
                            lista_limpa.append({
                                "E-mail": u.get("username"),
                                "Nome": u.get("nome"),
                                "Plano": "PRO 👑" if p.get("plano") == "premium" else "Grátis",
                                "Ofensiva": f"{p.get('streak', 0)} dias"
                            })
                        
                        df_admin = pd.DataFrame(lista_limpa)
                        st.dataframe(df_admin, use_container_width=True)
                    else:
                        st.write("Ainda não há usuários registrados no banco de dados.")
                except Exception as e:
                    st.error("Erro ao carregar dados do Supabase.")
