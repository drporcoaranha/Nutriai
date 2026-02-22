import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os
import re
import hashlib
from PIL import Image

# --- 1. CONFIGURAÇÃO DA PÁGINA (NutryAi) ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered") 
fuso_local = timezone(timedelta(hours=-3))

# --- 2. SISTEMA DE BANCO DE DADOS (USUÁRIOS E ISOLAMENTO) ---
ARQUIVO_USUARIOS = "usuarios_db.json"

def hash_senha(senha):
    """Criptografa a senha para não salvar em texto limpo."""
    return hashlib.sha256(str.encode(senha)).hexdigest()

def carregar_usuarios():
    if os.path.exists(ARQUIVO_USUARIOS):
        with open(ARQUIVO_USUARIOS, "r") as f:
            return json.load(f)
    return {}

def criar_conta(username, nome, senha):
    usuarios = carregar_usuarios()
    if username in usuarios:
        return False # Usuário já existe
    usuarios[username] = {"nome": nome, "senha": hash_senha(senha)}
    with open(ARQUIVO_USUARIOS, "w") as f:
        json.dump(usuarios, f)
    return True

def validar_login(username, senha):
    usuarios = carregar_usuarios()
    if username in usuarios:
        if usuarios[username]["senha"] == hash_senha(senha):
            return usuarios[username]["nome"]
    return None

# Funções de Estoque Isoladas por Usuário
def carregar_despensa(username):
    arquivo = f"despensa_{username}.csv"
    if os.path.exists(arquivo):
        return pd.read_csv(arquivo)
    else:
        # Despensa inicial padrão para novos usuários
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

# --- 3. VERIFICAÇÃO DE API ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        modelo = genai.GenerativeModel('gemini-2.5-flash') 
        api_configurada = True
    except Exception as e: pass

# --- 4. INICIALIZAÇÃO DE SESSÃO ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = None
if 'nome_usuario' not in st.session_state: st.session_state.nome_usuario = None
if 'despensa' not in st.session_state: st.session_state.despensa = None
if 'cardapio_atual' not in st.session_state: st.session_state.cardapio_atual = None
if 'cardapio_ideal' not in st.session_state: st.session_state.cardapio_ideal = None
if 'consumidos' not in st.session_state: st.session_state.consumidos = set()
if 'chat_history' not in st.session_state: st.session_state.chat_history = []

def fazer_logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- 5. CSS GLOBAL (Oculta menu e estiliza botões) ---
st.markdown(f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    .block-container {{padding-top: 2rem; padding-bottom: 5rem; max-width: 600px;}}
    .stApp {{ background-color: #F2F2F7 !important; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Helvetica, Arial, sans-serif !important; }}
    
    /* Cartões e Telas */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        background-color: #FFFFFF !important;
        border-radius: 14px !important;
        border: none !important;
        box-shadow: 0px 2px 10px rgba(0, 0, 0, 0.04) !important;
        padding: 15px !important;
    }}
    
    /* Estilo dos Botões */
    div[data-testid="stButton"] button, div[data-testid="stPopover"] > button {{
        border-radius: 20px !important; 
        height: 50px !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        border: 1px solid #E5E5EA !important;
        transition: all 0.2s ease-in-out !important;
    }}
    div[data-testid="stButton"] button[kind="primary"] {{
        background-color: #007AFF !important; 
        color: white !important;
        border: none !important;
    }}
    div[data-testid="stButton"] button[kind="primary"]:hover {{
        background-color: #0062CC !important;
        transform: scale(0.98);
    }}

    /* Tabelas e Barras de Progresso */
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th {{ color: #8E8E93 !important; font-weight: 600 !important; border-bottom: 1px solid #E5E5EA !important; text-align: left !important; padding-bottom: 8px !important; }}
    td, th {{ padding: 12px 8px !important; border-bottom: 1px solid #E5E5EA !important; border-top: none !important; border-left: none !important; border-right: none !important; }}
    tr:last-child td {{ border-bottom: none !important; }}
    
    .macro-bar-container {{ width: 100%; background-color: #E5E5EA; border-radius: 8px; height: 10px; margin-top: 4px; overflow: hidden; }}
    .macro-bar-fill {{ height: 100%; border-radius: 8px; transition: width 0.5s ease-in-out; }}
    .bg-kcal {{ background-color: #FF9500; }}
    .bg-prot {{ background-color: #34C759; }}
    .bg-carb {{ background-color: #007AFF; }}
    .bg-gord {{ background-color: #AF52DE; }}

    /* Fixar as abas no topo apenas na tela principal */
    .app-tabs > div[data-testid="stTabs"] > div:first-child {{
        position: -webkit-sticky;
        position: sticky;
        top: 0px;
        z-index: 999;
        background-color: rgba(242, 242, 247, 0.9);
        backdrop-filter: blur(10px);
        padding-top: 10px;
        padding-bottom: 10px;
        border-bottom: 1px solid rgba(60, 60, 67, 0.1);
    }}
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# MÓDULO 1: TELA DE LOGIN / CADASTRO
# ==========================================
if not st.session_state.logged_in:
    st.markdown("""
        <div style="text-align: center; margin-bottom: 30px; margin-top: 20px;">
            <h1 style="font-size: 4rem; margin-bottom: 0;">🍏</h1>
            <h1 style="font-weight: 800; color: #000;">NutryAi</h1>
            <p style="color: #8E8E93;">Inteligência em cada refeição.</p>
        </div>
    """, unsafe_allow_html=True)

    tab_login, tab_cadastro = st.tabs(["🔐 Entrar", "📝 Criar Conta"])

    with tab_login:
        with st.container(border=True):
            login_user = st.text_input("Usuário (Login)", key="log_user").lower()
            login_senha = st.text_input("Senha", type="password", key="log_pass")
            if st.button("Acessar Conta", use_container_width=True, type="primary"):
                if login_user and login_senha:
                    nome_valido = validar_login(login_user, login_senha)
                    if nome_valido:
                        st.session_state.logged_in = True
                        st.session_state.username = login_user
                        st.session_state.nome_usuario = nome_valido
                        st.session_state.despensa = carregar_despensa(login_user) # Carrega só o estoque desse usuário!
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")

    with tab_cadastro:
        with st.container(border=True):
            cad_nome = st.text_input("Como quer ser chamado?")
            cad_user = st.text_input("Crie um nome de usuário (ex: pablo123)").lower()
            cad_senha = st.text_input("Crie uma senha forte", type="password")
            if st.button("Criar Minha Conta", use_container_width=True, type="primary"):
                if cad_nome and cad_user and cad_senha:
                    if criar_conta(cad_user, cad_nome, cad_senha):
                        st.success("Conta criada com sucesso! Volte na aba 'Entrar' para acessar.")
                    else:
                        st.error("Esse usuário já existe. Tente outro nome.")
                else:
                    st.warning("Preencha todos os campos.")

# ==========================================
# MÓDULO 2: O APLICATIVO PRINCIPAL (LOGADO)
# ==========================================
else:
    hora_atual = datetime.now(fuso_local).hour
    if hora_atual < 12:
        saudacao = "Bom dia"
        icone_tempo = "☀️"
        msg_contexto = "Pronto para dominar sua insulina hoje?"
    elif hora_atual < 18:
        saudacao = "Boa tarde"
        icone_tempo = "☕"
        msg_contexto = "Mantendo o foco na sua rotina à tarde!"
    else:
        saudacao = "Boa noite"
        icone_tempo = "🌙"
        msg_contexto = "Quase lá, foco na reta final do seu dia."

    col_title, col_logout = st.columns([4, 1], vertical_alignment="center")
    with col_title:
        st.markdown(f"""
            <div style="padding-bottom: 10px; padding-top: 10px;">
                <h1 style="color: #000; font-weight: 800; font-size: 2rem; margin-bottom: 0;">NutryAi 🍏</h1>
                <p style="color: #8E8E93; font-size: 0.95rem; margin-top: -5px;"><b>{saudacao}, {st.session_state.nome_usuario}! {icone_tempo}</b><br>{msg_contexto}</p>
            </div>
        """, unsafe_allow_html=True)
    with col_logout:
        if st.button("Sair"): fazer_logout()

    # Adicionando uma classe wrapper para fixar as abas via CSS
    st.markdown('<div class="app-tabs">', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🕒 Agenda", "📦 Estoque", "🍽️ Seu Dia", "👩‍⚕️ Plano Ideal", "💬 Chat"])
    st.markdown('</div>', unsafe_allow_html=True)

    # --- ABA 1: ROTINA EM BLOCOS DE TEMPO ---
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

    # --- ABA 2: ESTOQUE & COMPRAS ---
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
                        salvar_despensa(st.session_state.despensa, st.session_state.username) # Salva para o usuário logado
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
        if estoque_zerado.empty:
            st.info("Tudo abastecido por enquanto.")
        else:
            st.warning("Atenção! Repor:")
            for index, row in estoque_zerado.iterrows(): st.write(f"- {row['Alimento']}")
        anotacoes = st.text_area("O que mais precisa trazer?", height=80, placeholder="Ex: Adoçante, café...")
        if st.button("Salvar Anotações", use_container_width=True): st.toast("✅ Anotações salvas!")

    # --- ABA 3: SEU DIA (GERADOR + AO VIVO) ---
    with tab3:
        if st.session_state.cardapio_atual is None:
            st.markdown("""
            <div style='text-align: center; padding: 30px 20px; background-color: #FFFFFF; border-radius: 14px; box-shadow: 0px 2px 10px rgba(0,0,0,0.04); margin-bottom: 20px; margin-top: 10px;'>
                <h1 style='font-size: 3.5rem; margin-bottom: 5px;'>🍽️</h1>
                <h3 style='color: #000000; font-weight: 700; margin-bottom: 5px;'>Seu dia em branco</h3>
                <p style='color: #8E8E93; font-size: 0.95rem; margin-bottom: 25px;'>Vamos criar um plano de ataque inteligente usando apenas o que tem na geladeira hoje.</p>
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("⚡ Gerar Cardápio de Hoje", use_container_width=True, type="primary"):
            if not api_configurada:
                st.error("⚠️ Configure a chave de API.")
            else:
                with st.spinner("Mapeando seu dia e criando a logística..."):
                    despensa_ativa = st.session_state.despensa[st.session_state.despensa["Quantidade"] > 0]
                    prompt = f"""
                    Nutricionista Clínico especialista em Resistência à Insulina (RI). Crie o cardápio real de hoje usando APENAS O ESTOQUE.
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
                    except Exception as e:
                        st.error(f"🚨 Erro na IA: {e}")

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

    # --- ABA 4: PLANO IDEAL (METAS FLEXÍVEIS) ---
    with tab4:
        if st.session_state.cardapio_ideal is None:
            st.markdown("""
            <div style='text-align: center; padding: 30px 20px; background-color: #FFFFFF; border-radius: 14px; box-shadow: 0px 2px 10px rgba(0,0,0,0.04); margin-bottom: 20px; margin-top: 10px;'>
                <h1 style='font-size: 3.5rem; margin-bottom: 5px;'>👩‍⚕️</h1>
                <h3 style='color: #000000; font-weight: 700; margin-bottom: 5px;'>Plano Padrão Ouro</h3>
                <p style='color: #8E8E93; font-size: 0.95rem; margin-bottom: 25px;'>A Nutri vai criar seu plano perfeito (ignorando o estoque) para você usar no mercado.</p>
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("✨ Descobrir Meu Plano Ideal", use_container_width=True, type="primary"):
            if not api_configurada:
                st.error("⚠️ Configure a chave de API.")
            else:
                with st.spinner("Calculando mapa nutricional..."):
                    prompt_ideal = f"""
                    Nutricionista especialista em RI e Dieta Flexível. Crie um PLANO DE METAS (Macros) e GUIA DE ESTRUTURAÇÃO DE PRATOS. IGNORAR ESTOQUE.
                    REGRAS: Carbo Complexo SEMPRE com Proteína/Gordura Boa. Nenhuma salada matinal.
                    AGENDA: Acorda {hora_acordar.strftime('%H:%M')} | Trab {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')} | Tempo cozinhar: {tempo_preparo} min.
                    Retorne JSON: {{"metas_diarias": {{"calorias": "2000 kcal", "carboidratos": "150g", "proteinas": "140g", "gorduras": "60g", "fibras": "30g"}}, "refeicoes": [{{"hora": "HH:MM", "nome": "Nome", "alvo_macros": "Carbos: 30g | Prot: 25g", "estrutura_prato": "Regra de porções", "sugestoes_flexiveis": "3 opções práticas", "instrucao_clinica": "Explicação clínica"}}]}}
                    """
                    try:
                        resposta_ideal = modelo.generate_content(prompt_ideal)
                        texto_limpo_ideal = re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL).group(0) if re.search(r'\{.*\}', resposta_ideal.text.strip(), re.DOTALL) else resposta_ideal.text.strip()
                        st.session_state.cardapio_ideal = json.loads(texto_limpo_ideal)
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Erro: {e}")
                        
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

    # --- ABA 5: CHAT COM A NUTRICIONISTA ---
    with tab5:
        st.markdown("### 💬 Chat com a Nutri")
        st.write("Dúvidas no restaurante a quilo? Envie a foto!")
        foto_upload = st.file_uploader("📸 Foto do prato ou rótulo", type=["jpg", "jpeg", "png"])
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        prompt_chat = st.chat_input("Mensagem...")
        if prompt_chat:
            if not api_configurada:
                st.error("⚠️ Configure a API.")
            else:
                st.session_state.chat_history.append({"role": "user", "content": prompt_chat})
                with st.chat_message("user"):
                    st.markdown(prompt_chat)
                    if foto_upload: st.image(foto_upload, width=250); st.caption("📷 Foto enviada.")
                with st.chat_message("assistant"):
                    with st.spinner("A Nutri está digitando..."):
                        try:
                            conteudo_ia = ["Você é a NutryAi, Nutricionista Clínica especialista em Resistência à Insulina e Dieta Flexível. Seja prestativa, use tom amigável. Avalie impactos na insulina se o paciente perguntar sobre alimentos ou fotos.", prompt_chat]
                            if foto_upload:
                                imagem_pil = Image.open(foto_upload)
                                conteudo_ia.append(imagem_pil)
                            resposta_chat = modelo.generate_content(conteudo_ia)
                            st.markdown(resposta_chat.text)
                            st.session_state.chat_history.append({"role": "assistant", "content": resposta_chat.text})
                        except Exception as e: st.error(f"Erro na resposta: {e}")
