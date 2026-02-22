import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os
import re
from PIL import Image

# --- 1. CONFIGURAÇÃO DA PÁGINA (NutryAi) ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered") 

# Injetando CSS SUPER CUSTOMIZADO (Estilo Nativo iOS Lapidado)
st.markdown("""
    <style>
    /* 1. Esconder menu nativo e ajustar espaçamentos */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 5rem; max-width: 600px;}
    
    /* 2. Fundo Cinza Claro do iOS e Fonte SF Pro */
    .stApp {
        background-color: #F2F2F7 !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif !important;
    }

    /* 3. Título Estilo iOS (Centralizado) */
    .app-header {
        text-align: center;
        padding-bottom: 10px;
        padding-top: 10px;
    }
    .app-header h1 {
        color: #000000;
        font-weight: 800;
        font-size: 2.2rem;
        letter-spacing: -0.5px;
        margin-bottom: 0px;
    }
    .app-header p {
        color: #8E8E93;
        font-size: 1rem;
        margin-top: -10px;
        font-weight: 500;
    }

    /* 4. Abas Fixas Estilo Segmented Control Apple */
    div[data-testid="stTabs"] > div:first-child {
        position: -webkit-sticky;
        position: sticky;
        top: 0px;
        z-index: 999;
        background-color: rgba(242, 242, 247, 0.9);
        backdrop-filter: blur(10px);
        padding-top: 10px;
        padding-bottom: 10px;
        border-bottom: 1px solid rgba(60, 60, 67, 0.1);
    }
    
    /* 5. Cartões Brancos Flutuantes (Cards do iOS) */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: #FFFFFF !important;
        border-radius: 14px !important;
        border: none !important;
        box-shadow: 0px 2px 10px rgba(0, 0, 0, 0.04) !important;
        padding: 15px !important;
    }
    
    /* 6. Botões Principais Estilo Apple */
    div[data-testid="stButton"] button {
        border-radius: 14px !important; 
        height: 50px !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        border: none !important;
        transition: all 0.2s ease-in-out !important;
    }
    
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #007AFF !important; 
        color: white !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #0062CC !important;
        transform: scale(0.98);
    }

    /* 7. Botões Redondos de Ação Perfeitos (Círculos Absolutos) */
    div[data-testid="stPopover"] {
        display: flex !important;
        justify-content: center !important; /* Força o botão pro meio da coluna */
    }
    div[data-testid="stPopover"] > button {
        width: 60px !important;
        height: 60px !important;
        min-width: 60px !important;
        max-width: 60px !important;
        min-height: 60px !important;
        max-height: 60px !important;
        border-radius: 50% !important; /* Círculo perfeito */
        padding: 0 !important;
        font-size: 24px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.1) !important;
        border: 1px solid #E5E5EA !important;
        transition: transform 0.1s ease-in-out !important;
    }
    div[data-testid="stPopover"] > button:active {
        transform: scale(0.9) !important;
        background-color: #F2F2F7 !important;
    }

    /* 8. Balões do Chat Estilo iMessage */
    div[data-testid="stChatMessage"] {
        border-radius: 18px !important;
        padding: 12px 16px !important;
        border: none !important;
    }
    div[data-testid="stChatMessage"]:nth-child(even) {
        background-color: #E9E9EB !important; 
        color: black !important;
    }
    
    </style>
    
    <div class="app-header">
        <h1>NutryAi 🍏</h1>
        <p>Sua rotina flexível e inteligente</p>
    </div>
    """, unsafe_allow_html=True)

# --- 2. LÓGICA DE MEMÓRIA E ARQUIVOS ---
ARQUIVO_DESPENSA = "despensa_inteligente_ri.csv" 

def carregar_despensa():
    if os.path.exists(ARQUIVO_DESPENSA):
        return pd.read_csv(ARQUIVO_DESPENSA)
    else:
        df = pd.DataFrame({
            "Alimento": [
                "Ovos", "Goma de Tapioca", "Pão (Francês ou Integral)", 
                "Patinho Moído", "Cenoura", "Peito de Frango",
                "Aveia em Flocos", "Semente de Chia", "Iogurte Natural", 
                "Maçã", "Arroz e Feijão (Prontos)", "Azeite de Oliva Extravirgem"
            ],
            "Quantidade": [30.0, 500.0, 4.0, 500.0, 3.0, 500.0, 300.0, 150.0, 500.0, 8.0, 1000.0, 1.0],
            "Unidade": ["un", "g", "un", "g", "un", "g", "g", "g", "g", "un", "g", "vidro"],
            "Pronto/Rápido": ["Sim", "Sim", "Sim", "Não", "Sim", "Não", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim"]
        })
        df.to_csv(ARQUIVO_DESPENSA, index=False)
        return df

def salvar_despensa(df):
    df.to_csv(ARQUIVO_DESPENSA, index=False)

# --- 3. VERIFICAÇÃO SEGURA DA CHAVE DE API ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        modelo = genai.GenerativeModel('gemini-2.5-flash') 
        api_configurada = True
    except Exception as e:
        pass

fuso_local = timezone(timedelta(hours=-3))

# --- 4. INICIALIZAÇÃO DE VARIÁVEIS NA SESSÃO ---
if 'despensa' not in st.session_state:
    st.session_state.despensa = carregar_despensa()
if 'cardapio_atual' not in st.session_state:
    st.session_state.cardapio_atual = None
if 'cardapio_ideal' not in st.session_state: 
    st.session_state.cardapio_ideal = None
if 'consumidos' not in st.session_state:
    st.session_state.consumidos = set()
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# --- 5. INTERFACE VISUAL (ABAS) ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🕒 Agenda", "📦 Estoque", "🍽️ Seu Dia", "👩‍⚕️ Plano Ideal", "💬 Chat"])

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
    
    # Colunas proporcionais para centralizar os botões
    c_espaco_esq, col_add, col_rem, c_espaco_dir = st.columns([1.5, 1, 1, 1.5])
    
    with col_add:
        # ATENÇÃO: Tirei o use_container_width=True daqui para não achatar o círculo!
        with st.popover("➕"):
            st.markdown("#### Novo Alimento")
            novo_nome = st.text_input("Alimento")
            nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
            nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un", "dose", "colher"])
            novo_pronto = st.radio("Preparo Rápido?", ["Não", "Sim"], horizontal=True)
            if st.button("Salvar", type="primary"):
                if novo_nome:
                    novo_item = pd.DataFrame({"Alimento": [novo_nome], "Quantidade": [nova_qtd], "Unidade": [nova_unidade], "Pronto/Rápido": [novo_pronto]})
                    st.session_state.despensa = pd.concat([st.session_state.despensa, novo_item], ignore_index=True)
                    salvar_despensa(st.session_state.despensa)
                    st.toast("✅ Item guardado!")
                    st.rerun()
    
    with col_rem:
        # ATENÇÃO: Tirei o use_container_width=True daqui também!
        with st.popover("🗑️"):
            st.markdown("#### Excluir Alimento")
            lista_alimentos = st.session_state.despensa["Alimento"].tolist()
            item_remover = st.selectbox("Apagar:", lista_alimentos)
            if st.button("Excluir", type="primary"):
                st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                salvar_despensa(st.session_state.despensa)
                st.toast("🗑️ Item removido!")
                st.rerun()

    st.write("") # Espaçamento respirável
    df_visual = st.session_state.despensa.copy()
    def formatar_estoque(row):
        return "❌ ESGOTADO" if row["Quantidade"] <= 0 else f"{row['Quantidade']} {row['Unidade']}"
    df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
    st.dataframe(df_visual[["Alimento", "Disponível", "Pronto/Rápido"]], use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 📝 Lista do Mercado")
    
    estoque_zerado = st.session_state.despensa[st.session_state.despensa["Quantidade"] <= 0]
    if estoque_zerado.empty:
        st.info("Tudo abastecido por enquanto.")
    else:
        st.warning("Atenção! Repor:")
        for index, row in estoque_zerado.iterrows():
            st.write(f"- {row['Alimento']}")
            
    anotacoes = st.text_area("O que mais precisa trazer?", height=80, placeholder="Ex: Adoçante, café...")
    if st.button("Salvar Anotações", use_container_width=True): 
        st.toast("✅ Anotações salvas!")

# --- ABA 3: SEU DIA (GERADOR + AO VIVO) ---
with tab3:
    st.markdown("### 🍽️ Plano de Ação")
    st.write("Baseado no que você tem em casa agora.")
    
    if st.button("Gerar Cardápio de Hoje", use_container_width=True, type="primary"):
        if not api_configurada:
            st.error("⚠️ Configure a chave de API.")
        else:
            with st.spinner("Calculando logística..."):
                despensa_ativa = st.session_state.despensa[st.session_state.despensa["Quantidade"] > 0]
                prompt = f"""
                Você é um Nutricionista Clínico especialista em Resistência à Insulina (RI).
                Crie o cardápio real de hoje usando APENAS O ESTOQUE.
                REGRA: NUNCA sugira carboidratos "solteiros".
                REGRAS CULTURAIS: NUNCA sugira salada verde de manhã. Use aveia/chia/fruta para bater fibra matinal.
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
                    st.toast("✅ Plano pronto!")
                except Exception as e:
                    st.error(f"🚨 Erro na IA: {e}")

    if st.session_state.cardapio_atual is not None:
        st.divider()
        hora_agora = datetime.now(fuso_local).strftime("%H:%M")
        
        with st.container(border=True):
            st.markdown(f"#### 🎯 Progresso (Agora: {hora_agora})")
            resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🔥 Kcal", resumo.get('calorias_totais', '0'))
            c2.metric("🥩 Prot", resumo.get('proteinas_totais', '0g'))
            c3.metric("🌾 Carb", resumo.get('carbos_totais', '0g'))
            c4.metric("🥑 Gord", resumo.get('gorduras_totais', '0g'))

        refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
        total_refeicoes = len(refeicoes)
        st.progress(len(st.session_state.consumidos) / total_refeicoes if total_refeicoes > 0 else 0)
        
        for i, ref in enumerate(refeicoes):
            id_ref = f"ref_{i}"
            ja_consumido = id_ref in st.session_state.consumidos
            with st.container(border=True):
                col_texto, col_check = st.columns([4, 1], vertical_alignment="center")
                with col_texto:
                    st.markdown(f"**{'✅' if ja_consumido else '🕒'} {ref['hora']} | {ref['nome']}**")
                    st.write(f"🍽️ {ref['ingredientes']}")
                    st.caption(f"💡 {ref.get('instrucao_preparo', '')}")
                with col_check:
                    concluido = st.checkbox("Feito", key=f"check_{i}", value=ja_consumido, disabled=ja_consumido)
                    if concluido and not ja_consumido:
                        st.session_state.consumidos.add(id_ref)
                        for item in ref.get("uso_despensa", []):
                            idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == item.get("nome_exato")].tolist()
                            if idx: st.session_state.despensa.at[idx[0], 'Quantidade'] -= float(item.get("qtd_descontada", 0))
                        salvar_despensa(st.session_state.despensa)
                        st.toast(f"🎉 Refeição concluída!")
                        st.rerun()

# --- ABA 4: PLANO IDEAL (METAS FLEXÍVEIS) ---
with tab4:
    st.markdown("### 👩‍⚕️ Estrutura Ouro")
    st.write("A Nutri te entrega a estrutura perfeita para dominar a insulina. Use para fazer a lista do mercado!")
    
    if st.button("Descobrir Meu Plano Ideal", use_container_width=True, type="primary"):
        if not api_configurada:
            st.error("⚠️ Configure a chave de API.")
        else:
            with st.spinner("Calculando..."):
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
                    st.toast("✨ Plano Ouro gerado!")
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
    st.write("Dúvidas no mercado? Restaurante a quilo? Mande a foto.")

    foto_upload = st.file_uploader("📸 Foto do prato ou rótulo", type=["jpg", "jpeg", "png"])

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt_chat = st.chat_input("Mensagem...")
    
    if prompt_chat:
        if not api_configurada:
            st.error("⚠️ Configure a API.")
        else:
            st.session_state.chat_history.append({"role": "user", "content": prompt_chat})
            with st.chat_message("user"):
                st.markdown(prompt_chat)
                if foto_upload:
                    st.image(foto_upload, width=250)
                    st.caption("📷 Foto enviada.")

            with st.chat_message("assistant"):
                with st.spinner("A Nutri está digitando..."):
                    try:
                        conteudo_ia = [
                            "Você é a NutryAi, Nutricionista Clínica especialista em Resistência à Insulina e Dieta Flexível. Seja prestativa, use tom amigável. Avalie impactos na insulina se o paciente perguntar sobre alimentos ou fotos.",
                            prompt_chat
                        ]
                        if foto_upload:
                            imagem_pil = Image.open(foto_upload)
                            conteudo_ia.append(imagem_pil)

                        resposta_chat = modelo.generate_content(conteudo_ia)
                        st.markdown(resposta_chat.text)
                        st.session_state.chat_history.append({"role": "assistant", "content": resposta_chat.text})
                    
                    except Exception as e:
                        st.error(f"Erro na resposta: {e}")
