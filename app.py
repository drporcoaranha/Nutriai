import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA (Interface mais limpa) ---
st.set_page_config(page_title="Minha Dieta IA", page_icon="🍏", layout="centered") # 'centered' fica mais com cara de app no celular

# Injetando CSS personalizado para esconder o menu do Streamlit e deixar com cara de App nativo
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    </style>
    """, unsafe_allow_html=True)

st.title("🍏 Assistente de Nutrição")
st.caption("Seu planejamento inteligente de 24 horas.")

# --- LÓGICA DE MEMÓRIA E IA (Mantida igual, funcionando perfeitamente) ---
ARQUIVO_DESPENSA = "despensa.csv"

def carregar_despensa():
    if os.path.exists(ARQUIVO_DESPENSA):
        return pd.read_csv(ARQUIVO_DESPENSA)
    else:
        df = pd.DataFrame({
            "Alimento": ["Peito de Frango", "Arroz Branco", "Ovo", "Whey Protein"],
            "Quantidade": [500.0, 1000.0, 12.0, 900.0],
            "Unidade": ["g", "g", "un", "g"],
            "Pronto/Rápido": ["Não", "Não", "Sim", "Sim"]
        })
        df.to_csv(ARQUIVO_DESPENSA, index=False)
        return df

def salvar_despensa(df):
    df.to_csv(ARQUIVO_DESPENSA, index=False)

api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        CHAVE_API = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=CHAVE_API)
        modelo = genai.GenerativeModel('gemini-2.5-flash')
        api_configurada = True
    except Exception as e:
        pass

fuso_local = timezone(timedelta(hours=-3))

if 'despensa' not in st.session_state:
    st.session_state.despensa = carregar_despensa()
if 'cardapio_atual' not in st.session_state:
    st.session_state.cardapio_atual = None
if 'consumidos' not in st.session_state:
    st.session_state.consumidos = set()

# --- 2. NOVA INTERFACE VISUAL (ABAS) ---
tab1, tab2, tab3, tab4 = st.tabs(["🕒 Rotina", "🛒 Despensa", "🧠 Gerador", "🔴 Ao Vivo"])

# --- ABA 1: ROTINA (Em formato de Card) ---
with tab1:
    with st.container(border=True):
        st.subheader("Configuração do Dia")
        
        col1, col2 = st.columns(2)
        with col1:
            hora_acordar = st.time_input("☀️ Acordar", time(6, 0))
            hora_dormir = st.time_input("🌙 Dormir", time(23, 0))
        with col2:
            trabalho_inicio = st.time_input("💼 Início Trabalho", time(8, 0))
            trabalho_fim = st.time_input("🏠 Fim Trabalho", time(18, 0))
        
        st.divider()
        tempo_preparo = st.slider("⏱️ Tempo livre para cozinhar (minutos)", 0, 120, 20)
        
        if st.button("Salvar Rotina", use_container_width=True, type="primary"):
            st.session_state.cardapio_atual = None
            st.session_state.consumidos = set()
            st.success("Rotina salva com sucesso!")

# --- ABA 2: DESPENSA (Interface limpa e botões alinhados) ---
with tab2:
    with st.container(border=True):
        st.subheader("Gerenciar Estoque")
        
        col_add, col_rem = st.columns(2)
        
        with col_add:
            with st.popover("➕ Novo Alimento", use_container_width=True):
                novo_nome = st.text_input("Nome")
                nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
                nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un"])
                novo_pronto = st.radio("Preparo Rápido?", ["Não", "Sim"], horizontal=True)
                
                if st.button("Adicionar"):
                    if novo_nome:
                        novo_item = pd.DataFrame({"Alimento": [novo_nome], "Quantidade": [nova_qtd], "Unidade": [nova_unidade], "Pronto/Rápido": [novo_pronto]})
                        st.session_state.despensa = pd.concat([st.session_state.despensa, novo_item], ignore_index=True)
                        salvar_despensa(st.session_state.despensa)
                        st.rerun()
        
        with col_rem:
            with st.popover("🗑️ Remover", use_container_width=True):
                lista_alimentos = st.session_state.despensa["Alimento"].tolist()
                item_remover = st.selectbox("Selecione para apagar:", lista_alimentos)
                if st.button("Excluir Item"):
                    st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                    salvar_despensa(st.session_state.despensa)
                    st.rerun()

    st.write("📋 **Seu Estoque Atual:**")
    df_visual = st.session_state.despensa.copy()
    df_visual["Disponível"] = df_visual["Quantidade"].astype(str) + " " + df_visual["Unidade"]
    st.dataframe(df_visual[["Alimento", "Disponível", "Pronto/Rápido"]], use_container_width=True, hide_index=True)

# --- ABA 3: MOTOR DA IA (Botão com destaque total) ---
with tab3:
    st.info("A IA vai cruzar seus horários com o estoque atual e montar sua logística completa.")
    st.write("") # Espaçamento
    
    if st.button("⚡ Gerar Cardápio Inteligente", use_container_width=True, type="primary"):
        if not api_configurada:
            st.error("Configure sua chave de API nos secrets.")
        else:
            with st.spinner("Analisando estoque e calculando macros..."):
                dados_despensa = st.session_state.despensa.to_dict(orient="records")
                prompt = f"""
                Você é um nutricionista clínico e assistente de logística. 
                Monte um cardápio de 24h.
                ROTINA: Acordo: {hora_acordar.strftime('%H:%M')} | Durmo: {hora_dormir.strftime('%H:%M')} | Trabalho: {trabalho_inicio.strftime('%H:%M')} às {trabalho_fim.strftime('%H:%M')} | Tempo cozinhar: {tempo_preparo} min.
                DESPENSA DISPONÍVEL (Use estritamente estes alimentos): {dados_despensa}
                Retorne EXCLUSIVAMENTE em formato JSON puro. Estrutura:
                {{
                  "resumo_diario": {{ "calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g" }},
                  "refeicoes": [
                    {{ "hora": "HH:MM", "nome": "Nome", "ingredientes": "Qtd e Ingrediente", "instrucao_preparo": "Instrução breve", "macros": {{ "calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g" }}, "uso_despensa": [ {{ "nome_exato": "NOME EXATO DA DESPENSA", "qtd_descontada": 150 }} ] }}
                  ]
                }}
                """
                try:
                    resposta = modelo.generate_content(prompt)
                    texto_resposta = resposta.text.strip()
                    if texto_resposta.startswith("```json"): texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()
                    st.session_state.cardapio_atual = json.loads(texto_resposta)
                    st.session_state.consumidos = set()
                    st.rerun()
                except Exception as e:
                    st.error("Erro ao processar a IA. Tente novamente.")

# --- ABA 4: PAINEL AO VIVO (Cards Profissionais) ---
with tab4:
    hora_agora = datetime.now(fuso_local).strftime("%H:%M")
    
    if st.session_state.cardapio_atual is None:
        st.warning("Gere a estratégia na aba 'Gerador' para acompanhar seu dia.")
    else:
        # Resumo Diário em um Card estilizado
        with st.container(border=True):
            st.markdown(f"### 🎯 Resumo do Dia (Agora: {hora_agora})")
            resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🔥 Kcal", resumo.get('calorias_totais', '0'))
            c2.metric("🥩 Prot", resumo.get('proteinas_totais', '0g'))
            c3.metric("🌾 Carb", resumo.get('carbos_totais', '0g'))
            c4.metric("🥑 Gord", resumo.get('gorduras_totais', '0g'))

        # Refeições em Cards Individuais
        refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
        progresso = len(st.session_state.consumidos)
        total_refeicoes = len(refeicoes)
        
        st.progress(progresso / total_refeicoes if total_refeicoes > 0 else 0)
        
        for i, ref in enumerate(refeicoes):
            id_ref = f"ref_{i}"
            ja_consumido = id_ref in st.session_state.consumidos
            
            # Card individual para cada refeição
            with st.container(border=True):
                col_texto, col_check = st.columns([4, 1], vertical_alignment="center")
                
                with col_texto:
                    cor_status = "✅" if ja_consumido else "🕒"
                    st.markdown(f"**{cor_status} {ref['hora']} | {ref['nome']}**")
                    st.write(f"🍽️ {ref['ingredientes']}")
                    
                    macros = ref.get('macros', {})
                    st.caption(f"💡 {ref['instrucao_preparo']} | 🔥 {macros.get('calorias', 0)} kcal")
                
                with col_check:
                    concluido = st.checkbox("Baixa", key=f"check_{i}", value=ja_consumido, disabled=ja_consumido)
                    
                    if concluido and not ja_consumido:
                        st.session_state.consumidos.add(id_ref)
                        for item_usado in ref.get("uso_despensa", []):
                            nome_exato = item_usado.get("nome_exato")
                            qtd_descontar = item_usado.get("qtd_descontada", 0)
                            idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == nome_exato].tolist()
                            if idx:
                                linha = idx[0]
                                st.session_state.despensa.at[linha, 'Quantidade'] -= float(qtd_descontar)
                        salvar_despensa(st.session_state.despensa)
                        st.rerun()
