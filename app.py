import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os
import re
import hashlib
import urllib.parse
import requests
import base64
from io import BytesIO
from PIL import Image

# --- 1. CONFIGURAÇÃO DA PÁGINA (NutryAi) ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered", initial_sidebar_state="collapsed") 
fuso_local = timezone(timedelta(hours=-3))

# --- 2. CONFIGURAÇÕES DO GOOGLE LOGIN (OAUTH) ---
GOOGLE_CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = st.secrets.get("REDIRECT_URI", "http://localhost:8501") 

def gerar_url_google():
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "prompt": "select_account"
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"

# SVG Oficial do Google para o Botão
GOOGLE_SVG = """
<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" style="width:20px;height:20px;margin-right:10px;">
<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"></path>
<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"></path>
<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"></path>
<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"></path>
</svg>
"""

# --- 3. SISTEMA DE BANCO DE DADOS (USUÁRIOS E PERFIL) ---
ARQUIVO_USUARIOS = "usuarios_db.json"

def hash_senha(senha):
    return hashlib.sha256(str.encode(senha)).hexdigest()

def carregar_usuarios():
    if os.path.exists(ARQUIVO_USUARIOS):
        with open(ARQUIVO_USUARIOS, "r") as f:
            return json.load(f)
    return {}

def criar_conta(username, nome, senha):
    usuarios = carregar_usuarios()
    if username in usuarios: return False
    
    usuarios[username] = {
        "nome": nome, 
        "senha": hash_senha(senha),
        "perfil": {"idade": 30, "peso": 70.0, "altura": 170, "objetivo": "Emagrecimento Saudável", "atividade": "Moderadamente Ativo", "foto": None}
    }
    with open(ARQUIVO_USUARIOS, "w") as f: json.dump(usuarios, f)
    return True

def validar_login(username, senha):
    usuarios = carregar_usuarios()
    if username in usuarios and usuarios[username]["senha"] == hash_senha(senha):
        return usuarios[username] 
    return None

def salvar_perfil(username, nome_atualizado, perfil_data):
    usuarios = carregar_usuarios()
    if username in usuarios:
        usuarios[username]["nome"] = nome_atualizado
        usuarios[username]["perfil"] = perfil_data
        with open(ARQUIVO_USUARIOS, "w") as f: json.dump(usuarios, f)

def carregar_despensa(username):
    arquivo = f"despensa_{username}.csv"
    if os.path.exists(arquivo): return pd.read_csv(arquivo)
    else:
        df = pd.DataFrame({
            "Alimento": ["Ovos", "Goma de Tapioca", "Pão (Francês ou Integral)", "Patinho Moído", "Cenoura", "Peito de Frango", "Aveia em Flocos", "Semente de Chia", "Iogurte Natural", "Maçã"],
            "Quantidade": [12.0, 500.0, 4.0, 500.0, 3.0, 500.0, 300.0, 150.0, 500.0, 6.0],
            "Unidade": ["un", "g", "un", "g", "un", "g", "g", "g", "g", "un"],
            "Pronto/Rápido": ["Sim", "Sim", "Sim", "Não", "Sim", "Não", "Sim", "Sim", "Sim", "Sim"]
        })
        df.to_csv(arquivo, index=False)
        return df

def salvar_despensa(df, username):
    arquivo = f"despensa_{username}.csv"
    df.to_csv(arquivo, index=False)

def extrair_numero(texto):
    numeros = re.findall(r'\d+', str(texto))
    return int(numeros[0]) if numeros else 0

# --- 4. VERIFICAÇÃO DE API GEMINI ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        modelo = genai.GenerativeModel('gemini-2.5-flash') 
        api_configurada = True
    except Exception as e: pass

# --- 5. INICIALIZAÇÃO DE SESSÃO ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = None
if 'nome_usuario' not in st.session_state: st.session_state.nome_usuario = None
if 'perfil' not in st.session_state: st.session_state.perfil = {}
if 'despensa' not in st.session_state: st.session_state.despensa = None
if 'cardapio_atual' not in st.session_state: st.session_state.cardapio_atual = None
if 'cardapio_ideal' not in st.session_state: st.session_state.cardapio_ideal = None
if 'consumidos' not in st.session_state: st.session_state.consumidos = set()
if 'chat_history' not in st.session_state: st.session_state.chat_history = []

def fazer_logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.query_params.clear() 
    st.rerun()

# --- INTERCEPTADOR DO GOOGLE ---
if not st.session_state.logged_in and "code" in st.query_params:
    codigo_autorizacao = st.query_params["code"]
    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {"code": codigo_autorizacao, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"}
        res = requests.post(token_url, data=token_data)
        if res.status_code == 200:
            access_token = res.json().get("access_token")
            user_res = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if user_res.status_code == 200:
                google_user = user_res.json()
                st.session_state.logged_in = True
                st.session_state.username = google_user.get("email") 
                st.session_state.nome_usuario = google_user.get("given_name", "Usuário") 
                
                usuarios = carregar_usuarios()
                if st.session_state.username not in usuarios:
                    criar_conta(st.session_state.username, st.session_state.nome_usuario, "google_sso_senha_dummy")
                    usuarios = carregar_usuarios()
                
                st.session_state.perfil = usuarios[st.session_state.username].get("perfil", {})
                st.session_state.despensa = carregar_despensa(st.session_state.username)
                st.query_params.clear()
                st.rerun()
        else:
            st.error("Falha na autenticação com o Google.")
            st.query_params.clear()
    except Exception as e:
        st.error(f"Erro no login social: {e}")

# --- 6. CSS GLOBAL UX 3.5 ---
st.markdown(f"""
    <style>
    [data-testid="stSidebar"] {{ display: none !important; }}
    [data-testid="collapsedControl"] {{ display: none !important; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
    .block-container {{padding-top: 1rem; padding-bottom: 5rem; max-width: 600px;}}
    .stApp {{ background-color: #F2F2F7 !important; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Helvetica, Arial, sans-serif !important; }}
    
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        background-color: #FFFFFF !important; border-radius: 14px !important; border: none !important; box-shadow: 0px 2px 10px rgba(0, 0, 0, 0.04) !important; padding: 15px !important;
    }}
    
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {{
        border: 1px solid #D1D1D6 !important; border-radius: 10px !important; padding: 12px 14px !important; background-color: #FAFAFA !important; color: #000 !important;
    }}
    
    div[data-testid="stButton"] button, div[data-testid="stPopover"] > button {{
        border-radius: 20px !important; height: 45px !important; font-weight: 600 !important; font-size: 16px !important; border: 1px solid #E5E5EA !important; transition: all 0.2s ease-in-out !important;
    }}
    div[data-testid="stButton"] button[kind="primary"] {{
        background-color: #007AFF !important; color: white !important; border: none !important;
    }}
    
    /* BOTÃO DO GOOGLE (HTML NATIVO) */
    .btn-google-nativo {{
        display: flex; align-items: center; justify-content: center;
        background-color: #FFFFFF; color: #000000; border: 1px solid #D1D1D6;
        border-radius: 20px; height: 50px; font-weight: 600; font-size: 16px;
        text-decoration: none; width: 100%; transition: all 0.2s ease-in-out;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .btn-google-nativo:hover {{ background-color: #F8F8F8; transform: scale(0.98); }}

    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th {{ color: #8E8E93 !important; font-weight: 600 !important; border-bottom: 1px solid #E5E5EA !important; text-align: left !important; padding-bottom: 8px !important; }}
    td, th {{ padding: 12px 8px !important; border-bottom: 1px solid #E5E5EA !important; border-top: none !important; border-left: none !important; border-right: none !important; }}
    tr:last-child td {{ border-bottom: none !important; }}
    
    .macro-bar-container {{ width: 100%; background-color: #E5E5EA; border-radius: 8px; height: 10px; margin-top: 4px; overflow: hidden; }}
    .macro-bar-fill {{ height: 100%; border-radius: 8px; transition: width 0.5s ease-in-out; }}
    .bg-kcal {{ background-color: #FF9500; }} .bg-prot {{ background-color: #34C759; }} .bg-carb {{ background-color: #007AFF; }} .bg-gord {{ background-color: #AF52DE; }}

    .app-tabs > div[data-testid="stTabs"] > div:first-child {{
        position: -webkit-sticky; position: sticky; top: 0px; z-index: 999; background-color: rgba(242, 242, 247, 0.9); backdrop-filter: blur(10px); padding-top: 10px; padding-bottom: 10px; border-bottom: 1px solid rgba(60, 60, 67, 0.1);
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# MÓDULO 1: TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    st.markdown("""
        <div style="text-align: center; margin-bottom: 25px; margin-top: 20px;">
            <h1 style="font-size: 4rem; margin-bottom: 0;">🍏</h1>
            <h1 style="font-weight: 800; color: #000;">NutryAi</h1>
            <p style="color: #8E8E93;">Inteligência em cada refeição.</p>
        </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("<h4 style='text-align: center; margin-bottom: 15px;'>Acesse sua conta</h4>", unsafe_allow_html=True)
        login_user = st.text_input("Usuário", placeholder="ex: seu_nome", key="log_user")
        login_senha = st.text_input("Senha", type="password", placeholder="••••••••", key="log_pass")
        
        if st.button("Entrar", use_container_width=True, type="primary"):
            if login_user and login_senha:
                dados_usuario = validar_login(login_user, login_senha)
                if dados_usuario:
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    st.session_state.nome_usuario = dados_usuario["nome"]
                    st.session_state.perfil = dados_usuario.get("perfil", {})
                    st.session_state.despensa = carregar_despensa(login_user)
                    st.rerun()
                else: st.error("Usuário ou senha incorretos.")
            else: st.warning("Preencha todos os campos.")
                
        st.markdown("<div style='text-align: center; margin: 15px 0; color: #8E8E93;'>ou</div>", unsafe_allow_html=True)
        
        # BOTÃO DO GOOGLE OFICIAL (SVG)
        if GOOGLE_CLIENT_ID:
            st.markdown(f'<a href="{gerar_url_google()}" class="btn-google-nativo" target="_self">{GOOGLE_SVG} Continuar com o Google</a>', unsafe_allow_html=True)
        else:
            st.markdown(f'<a href="#" class="btn-google-nativo" target="_self" title="Requer configuração no Google Cloud">{GOOGLE_SVG} Continuar com o Google (Desativado)</a>', unsafe_allow_html=True)
            if st.button("🔌 Simular Login Rápido (Teste)"):
                st.session_state.logged_in = True
                st.session_state.username = "usuario_google"
                st.session_state.nome_usuario = "Visitante"
                usuarios = carregar_usuarios()
                if "usuario_google" not in usuarios:
                    criar_conta("usuario_google", "Visitante", "dummy")
                    usuarios = carregar_usuarios()
                st.session_state.perfil = usuarios["usuario_google"].get("perfil", {})
                st.session_state.despensa = carregar_despensa("usuario_google")
                st.rerun()

    with st.expander("Ainda não tem conta? Clique aqui para criar"):
        cad_nome = st.text_input("Como quer ser chamado?")
        cad_user = st.text_input("Crie um nome de usuário (ex: pablo123)").lower()
        cad_senha = st.text_input("Crie uma senha forte", type="password")
        if st.button("Criar Minha Conta", use_container_width=True):
            if cad_nome and cad_user and cad_senha:
                if criar_conta(cad_user, cad_nome, cad_senha): st.success("Conta criada! Pode fazer o login acima.")
                else: st.error("Esse usuário já existe. Tente outro nome.")

# ==========================================
# MÓDULO 2: O APLICATIVO (LOGADO)
# ==========================================
else:
    hora_atual = datetime.now(fuso_local).hour
    if hora_atual < 12: saudacao, icone_tempo = "Bom dia", "☀️"
    elif hora_atual < 18: saudacao, icone_tempo = "Boa tarde", "☕"
    else: saudacao, icone_tempo = "Boa noite", "🌙"

    # --- O NOVO HEADER (TÍTULO CENTRALIZADO E PERFIL À DIREITA) ---
    col_empty, col_title, col_profile = st.columns([1, 2.5, 1], vertical_alignment="center")
    
    with col_title:
        st.markdown(f"""
            <div style="text-align: center; padding-top: 5px;">
                <h1 style="color: #000; font-weight: 800; font-size: 2rem; margin-bottom: 0;">NutryAi 🍏</h1>
                <p style="color: #8E8E93; font-size: 0.9rem; margin-top: -5px;">{saudacao}, {st.session_state.nome_usuario}!</p>
            </div>
        """, unsafe_allow_html=True)
        
    with col_profile:
        # GAVETA RETRÁTIL COM SUB-ABAS E FOTO
        with st.popover("⚙️ Perfil", use_container_width=True):
            tab_dados, tab_bio = st.tabs(["👤 Dados", "⚖️ Biometria"])
            
            p_idade = st.session_state.perfil.get("idade", 30)
            p_peso = st.session_state.perfil.get("peso", 70.0)
            p_altura = st.session_state.perfil.get("altura", 170)
            p_obj = st.session_state.perfil.get("objetivo", "Emagrecimento Saudável")
            p_atv = st.session_state.perfil.get("atividade", "Moderadamente Ativo")
            foto_salva = st.session_state.perfil.get("foto", None)
            
            with tab_dados:
                st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
                if foto_salva:
                    st.markdown(f'<img src="data:image/jpeg;base64,{foto_salva}" width="100" height="100" style="border-radius:50%; object-fit:cover; margin-bottom:10px; border: 2px solid #E5E5EA;">', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="font-size: 60px; margin-bottom: 10px;">👤</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                
                nova_foto = st.file_uploader("Trocar foto", type=["jpg", "png", "jpeg"])
                novo_nome = st.text_input("Seu Nome", value=st.session_state.nome_usuario)
                nova_idade = st.number_input("Idade", min_value=10, max_value=120, value=p_idade)

            with tab_bio:
                novo_peso = st.number_input("Peso (kg)", min_value=30.0, max_value=250.0, value=float(p_peso), step=0.5)
                nova_altura = st.number_input("Altura (cm)", min_value=100, max_value=230, value=int(p_altura))
                
                objetivos = ["Emagrecimento Saudável", "Hipertrofia (Massa)", "Manutenção", "Controle Glicêmico"]
                novo_obj = st.selectbox("Objetivo", objetivos, index=objetivos.index(p_obj) if p_obj in objetivos else 0)
                
                atividades = ["Sedentário", "Levemente Ativo", "Moderadamente Ativo", "Muito Ativo"]
                nova_atv = st.selectbox("Atividade", atividades, index=atividades.index(p_atv) if p_atv in atividades else 1)
            
            if st.button("💾 Salvar Perfil", type="primary", use_container_width=True):
                # Processamento da imagem para Base64
                if nova_foto is not None:
                    img = Image.open(nova_foto)
                    img.thumbnail((200, 200)) # Corta a imagem pra não pesar o banco
                    buffered = BytesIO()
                    img.convert('RGB').save(buffered, format="JPEG")
                    foto_salva = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                novo_perfil = {"idade": nova_idade, "peso": novo_peso, "altura": nova_altura, "objetivo": novo_obj, "atividade": nova_atv, "foto": foto_salva}
                st.session_state.perfil = novo_perfil
                st.session_state.nome_usuario = novo_nome
                salvar_perfil(st.session_state.username, novo_nome, novo_perfil)
                st.rerun() 
            
            st.divider()
            if st.button("🚪 Sair da Conta", use_container_width=True):
                fazer_logout()

    dados_perfil_ia = f"Paciente de {st.session_state.perfil.get('idade', 30)} anos, {st.session_state.perfil.get('peso', 70)}kg, {st.session_state.perfil.get('altura', 170)}cm. Objetivo: {st.session_state.perfil.get('objetivo', 'Emagrecimento')}. Atividade: {st.session_state.perfil.get('atividade', 'Moderada')}."

    st.markdown('<div class="app-tabs">', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🕒 Agenda", "📦 Estoque", "🍽️ Seu Dia", "👩‍⚕️ Plano Ideal", "💬 Chat"])
    st.markdown('</div>', unsafe_allow_html=True)

    with tab1:
        with st.container(border=True):
            st.subheader("Blocos Ocupados")
            c1, c2 = st.columns(2)
            hora_acordar = c1.time_input("☀️ Acordar", time(6, 30))
            hora_dormir = c2.time_input("🌙 Dormir", time(23, 0))
            c3, c4 = st.columns(2)
            trab_inicio = c3.time_input("💼 Trab. Início", time(8, 0), key="t_i")
            trab_fim = c4.time_input("💼 Trab. Fim", time(17, 30), key="t_f")
            c5, c6 = st.columns(2)
            transito_inicio = c5.time_input("🚗 Trâns. Início", time(17, 30), key="tr_i")
            transito_fim = c6.time_input("🏁 Trâns. Fim", time(18, 30), key="tr_f")
            c7, c8 = st.columns(2)
            treino_inicio = c7.time_input("💪 Treino Início", time(19, 0), key="tre_i")
            treino_fim = c8.time_input("🚿 Treino Fim", time(20, 0), key="tre_f")
            c9, c10 = st.columns(2)
            estudo_inicio = c9.time_input("📚 Estudo Início", time(20, 30), key="est_i")
            estudo_fim = c10.time_input("📝 Estudo Fim", time(22, 0), key="est_f")
            st.divider()
            tempo_preparo = st.slider("⏱️ Tempo para cozinhar (min/dia)", 0, 120, 30)
            if st.button("Salvar Horários", use_container_width=True, type="primary"):
                st.session_state.cardapio_atual = None
                st.session_state.cardapio_ideal = None 
                st.session_state.consumidos = set()
                st.success("✅ Ajustes salvos no sistema.")

    with tab2:
        st.markdown("### 🛒 Seu Estoque")
        col_add, col_rem = st.columns(2)
        with col_add:
            with st.popover("➕ Novo", use_container_width=True):
                st.markdown("#### Adicionar Alimento")
                novo_nome = st.text_input("Alimento")
                nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
                nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un", "dose", "colher"])
                novo_pronto = st.radio("Preparo Rápido?", ["Não", "Sim"], horizontal=True)
                if st.button("Salvar", type="primary"):
                    if novo_nome:
                        novo_item = pd.DataFrame({"Alimento": [novo_nome], "Quantidade": [nova_qtd], "Unidade": [nova_unidade], "Pronto/Rápido": [novo_pronto]})
                        st.session_state.despensa = pd.concat([st.session_state.despensa, novo_item], ignore_index=True)
                        salvar_despensa(st.session_state.despensa, st.session_state.username) 
                        st.toast("✅ Item guardado!")
                        st.rerun()
        with col_rem:
            with st.popover("🗑️ Remover", use_container_width=True):
                st.markdown("#### Excluir Alimento")
                lista_alimentos = st.session_state.despensa["Alimento"].tolist()
                item_remover = st.selectbox("Apagar:", lista_alimentos)
                if st.button("Excluir", type="primary"):
                    st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                    salvar_despensa(st.session_state.despensa, st.session_state.username)
                    st.toast("🗑️ Item removido!")
                    st.rerun()
        st.write("") 
        df_visual = st.session_state.despensa.copy()
        def formatar_estoque(row): return "❌ ESGOTADO" if row["Quantidade"] <= 0 else f"{row['Quantidade']} {row['Unidade']}"
        df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
        df_visual.set_index("Alimento", inplace=True)
        st.table(df_visual[["Disponível", "Pronto/Rápido"]])
        st.divider()
        st.markdown("### 📝 Lista do Mercado")
        estoque_zerado = st.session_state.despensa[st.session_state.despensa["Quantidade"] <= 0]
        if estoque_zerado.empty: st.info("Tudo abastecido por enquanto.")
        else:
            st.warning("Atenção! Repor:")
            for index, row in estoque_zerado.iterrows(): st.write(f"- {row['Alimento']}")
        anotacoes = st.text_area("O que mais precisa trazer?", height=80, placeholder="Ex: Adoçante, café...")
        if st.button("Salvar Anotações", use_container_width=True): st.toast("✅ Anotações salvas!")

    with tab3:
        if st.session_state.cardapio_atual is None:
            st.markdown("""
            <div style='text-align: center; padding: 30px 20px; background-color: #FFFFFF; border-radius: 14px; box-shadow: 0px 2px 10px rgba(0,0,0,0.04); margin-bottom: 20px; margin-top: 10px;'>
                <h1 style='font-size: 3.5rem; margin-bottom: 5px;'>🍽️</h1>
                <h3 style='color: #000000; font-weight: 700; margin-bottom: 5px;'>Seu dia em branco</h3>
                <p style='color: #8E8E93; font-size: 0.95rem; margin-bottom: 25px;'>Vamos criar um plano usando seu biotipo e o que tem na geladeira hoje.</p>
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("⚡ Gerar Cardápio de Hoje", use_container_width=True, type="primary"):
            if not api_configurada: st.error("⚠️ Configure a chave de API.")
            else:
                with st.spinner("Analisando sua biometria e calculando..."):
                    despensa_ativa = st.session_state.despensa[st.session_state.despensa["Quantidade"] > 0]
                    prompt = f"""
                    Nutricionista Clínico especialista em RI. Crie o cardápio real de hoje usando APENAS O ESTOQUE.
                    BIOMETRIA: {dados_perfil_ia}
                    REGRA: NUNCA sugira carboidratos "solteiros". NUNCA sugira salada verde de manhã. Use aveia/chia/fruta matinal.
                    AGENDA: Acorda {hora_acordar.strftime('%H:%M')} | Trab {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')} | Prep. Máx: {tempo_preparo} min.
                    ESTOQUE: {despensa_ativa.to_dict(orient="records")}
                    Retorne JSON: {{"resumo_diario": {{"calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "ingredientes": "Qtd", "instrucao_preparo": "Instrução", "macros": {{"calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g"}}, "uso_despensa": [{{"nome_exato": "NOME", "qtd_descontada": 150}}]}}]}}
                    """
                    try:
                        resposta = modelo.generate_content(prompt)
                        texto_limpo = re.search(r'\{.*\}', resposta.text.strip(), re.DOTALL).group(0) if re.search(r'\{.*\}', resposta.text.strip(), re.DOTALL) else resposta.text.strip()
                        st.session_state.cardapio_atual = json.loads(texto_limpo)
                        st.session_state.consumidos = set()
                        st.balloons() 
                        st.rerun()
                    except Exception as e: st.error(f"🚨 Erro na IA: {e}")

        if st.session_state.cardapio_atual is not None:
            hora_agora = datetime.now(fuso_local).strftime("%H:%M")
            resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
            refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
            tot_kcal = extrair_numero(resumo.get('calorias_totais', 0))
            tot_prot = extrair_numero(resumo.get('proteinas_totais', 0))
            tot_carb = extrair_numero(resumo.get('carbos_totais', 0))
            tot_gord = extrair_numero(resumo.get('gorduras_totais', 0))
            cons_kcal = cons_prot = cons_carb = cons_gord = 0
            for i, ref in enumerate(refeicoes):
                if f"ref_{i}" in st.session_state.consumidos:
                    cons_kcal += extrair_numero(ref.get('macros', {}).get('calorias', 0))
                    cons_prot += extrair_numero(ref.get('macros', {}).get('proteinas', 0))
                    cons_carb += extrair_numero(ref.get('macros', {}).get('carbos', 0))
                    cons_gord += extrair_numero(ref.get('macros', {}).get('gorduras', 0))
            pct_kcal = min(100, int((cons_kcal / tot_kcal * 100) if tot_kcal > 0 else 0))
            pct_prot = min(100, int((cons_prot / tot_prot * 100) if tot_prot > 0 else 0))
            pct_carb = min(100, int((cons_carb / tot_carb * 100) if tot_carb > 0 else 0))
            pct_gord = min(100, int((cons_gord / tot_gord * 100) if tot_gord > 0 else 0))

            st.markdown(f"### 🎯 Gamificação do Dia")
            with st.container(border=True):
                st.markdown(f"<p style='color: #8E8E93; font-size: 0.85rem; margin-bottom: 10px;'>PROGRESSO DOS MACROS • {hora_agora}</p>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"**🔥 Kcal**<br><span style='font-size: 0.8rem; color: #8E8E93;'>{cons_kcal}/{tot_kcal}</span><div class='macro-bar-container'><div class='macro-bar-fill bg-kcal' style='width: {pct_kcal}%;'></div></div>", unsafe_allow_html=True)
                c2.markdown(f"**🥩 Prot**<br><span style='font-size: 0.8rem; color: #8E8E93;'>{cons_prot}/{tot_prot}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-prot' style='width: {pct_prot}%;'></div></div>", unsafe_allow_html=True)
                c3.markdown(f"**🌾 Carb**<br><span style='font-size: 0.8rem; color: #8E8E93;'>{cons_carb}/{tot_carb}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-carb' style='width: {pct_carb}%;'></div></div>", unsafe_allow_html=True)
                c4.markdown(f"**🥑 Gord**<br><span style='font-size: 0.8rem; color: #8E8E93;'>{cons_gord}/{tot_gord}g</span><div class='macro-bar-container'><div class='macro-bar-fill bg-gord' style='width: {pct_gord}%;'></div></div>", unsafe_allow_html=True)

            st.write("")
            st.markdown("### 🗺️ Rota de Hoje")
            for i, ref in enumerate(refeicoes):
                id_ref = f"ref_{i}"
                ja_consumido = id_ref in st.session_state.consumidos
                with st.container(border=True):
                    col_texto, col_check = st.columns([4, 1], vertical_alignment="center")
                    with col_texto:
                        cor_icone = "🟢" if ja_consumido else "⚪"
                        st.markdown(f"**{cor_icone} {ref['hora']} | {ref['nome']}**")
                        st.write(f"🍽️ {ref['ingredientes']}")
                        st.caption(f"💡 {ref.get('instrucao_preparo', '')}")
                    with col_check:
                        concluido = st.checkbox("Baixa", key=f"check_{i}", value=ja_consumido, disabled=ja_consumido)
                        if concluido and not ja_consumido:
                            st.session_state.consumidos.add(id_ref)
                            for item in ref.get("uso_despensa", []):
                                idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == item.get("nome_exato")].tolist()
                                if idx: st.session_state.despensa.at[idx[0], 'Quantidade'] -= float(item.get("qtd_descontada", 0))
                            salvar_despensa(st.session_state.despensa, st.session_state.username)
                            st.toast(f"🎉 Rumo à meta! Refeição concluída.")
                            st.rerun()
                if i < len(refeicoes) - 1:
                    st.markdown("<div style='width: 3px; height: 25px; background-color: #E5E5EA; margin-left: 30px; margin-top: -15px; margin-bottom: -15px; border-radius: 2px; z-index: 1; position: relative;'></div>", unsafe_allow_html=True)

    with tab4:
        if st.session_state.cardapio_ideal is None:
            st.markdown("""
            <div style='text-align: center; padding: 30px 20px; background-color: #FFFFFF; border-radius: 14px; box-shadow: 0px 2px 10px rgba(0,0,0,0.04); margin-bottom: 20px; margin-top: 10px;'>
                <h1 style='font-size: 3.5rem; margin-bottom: 5px;'>👩‍⚕️</h1>
                <h3 style='color: #000000; font-weight: 700; margin-bottom: 5px;'>Plano Padrão Ouro</h3>
                <p style='color: #8E8E93; font-size: 0.95rem; margin-bottom: 25px;'>A Nutri vai criar seu plano perfeito para você usar no mercado.</p>
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("✨ Descobrir Meu Plano Ideal", use_container_width=True, type="primary"):
            if not api_configurada: st.error("⚠️ Configure a chave de API.")
            else:
                with st.spinner("Calculando o mapa nutricional para o seu biotipo..."):
                    prompt_ideal = f"""
                    Nutricionista especialista em RI. Crie um PLANO DE METAS e GUIA DE ESTRUTURAÇÃO DE PRATOS. IGNORAR ESTOQUE.
                    BIOMETRIA: {dados_perfil_ia}
                    REGRAS: Carbo Complexo SEMPRE com Proteína/Gordura Boa. Nenhuma salada matinal.
                    AGENDA: Acorda {hora_acordar.strftime('%H:%M')} | Trab {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')} | Tempo cozinhar: {tempo_preparo} min.
                    Retorne JSON: {{"metas_diarias": {{"calorias": "2000 kcal", "carboidratos": "150g", "proteinas": "140g", "gorduras": "60g", "fibras": "30g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "alvo_macros": "Carbos: 30g | Prot: 25g", "estrutura_prato": "Regra de porções", "sugestoes_flexiveis": "3 opções", "instrucao_clinica": "Explicação clínica"}}]}}
                    """
                    try:
                        resposta_ideal = modelo.generate_content(prompt_ideal)
                        texto_limpo_ideal = re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL).group(0) if re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL) else resposta_ideal.text.strip()
                        st.session_state.cardapio_ideal = json.loads(texto_limpo_ideal)
                        st.rerun()
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

    with tab5:
        st.markdown("### 💬 Chat com a Nutri")
        st.write("Dúvidas no restaurante a quilo? Envie a foto!")
        foto_upload = st.file_uploader("📸 Foto do prato ou rótulo", type=["jpg", "jpeg", "png"])
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        prompt_chat = st.chat_input("Mensagem...")
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
