import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA (NutryAi) ---
st.set_page_config(page_title="NutryAi", page_icon="🍏", layout="centered") 

# Injetando CSS personalizado para esconder o menu do Streamlit
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    </style>
    """, unsafe_allow_html=True)

st.title("🍏 NutryAi")
st.caption("Seu assistente de nutrição e gestão de tempo em blocos.")

# --- 2. LÓGICA DE MEMÓRIA E ARQUIVOS ---
ARQUIVO_DESPENSA = "despensa.csv"

def carregar_despensa():
    if os.path.exists(ARQUIVO_DESPENSA):
        return pd.read_csv(ARQUIVO_DESPENSA)
    else:
        df = pd.DataFrame({
            "Alimento": ["Peito de Frango", "Arroz Branco", "Ovo", "Whey Protein", "Banana", "Barra de Cereal"],
            "Quantidade": [500.0, 1000.0, 12.0, 900.0, 6.0, 5.0],
            "Unidade": ["g", "g", "un", "g", "un", "un"],
            "Pronto/Rápido": ["Não", "Não", "Sim", "Sim", "Sim", "Sim"]
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
if 'consumidos' not in st.session_state:
    st.session_state.consumidos = set()

# --- 5. INTERFACE VISUAL (ABAS) ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🕒 Agenda", "📦 Estoque", "🧠 Gerador", "🔴 Ao Vivo", "📝 Compras"])

# --- ABA 1: ROTINA EM BLOCOS DE TEMPO (REORGANIZADA PARA UX MOBILE) ---
with tab1:
    with st.container(border=True):
        st.subheader("Blocos de Tempo Ocupado")
        st.write("Defina seus horários. A IA usará os **buracos** da sua agenda para encaixar as refeições.")
        
        st.markdown("#### ☀️ Descanso")
        c1, c2 = st.columns(2)
        hora_acordar = c1.time_input("Acordar", time(6, 30))
        hora_dormir = c2.time_input("Dormir", time(23, 0))
        
        st.markdown("#### 💼 Trabalho")
        c3, c4 = st.columns(2)
        trab_inicio = c3.time_input("Início", time(8, 0), key="t_i")
        trab_fim = c4.time_input("Fim", time(17, 30), key="t_f")
        
        st.markdown("#### 🚗 Trânsito / Deslocamento")
        c5, c6 = st.columns(2)
        transito_inicio = c5.time_input("Início", time(17, 30), key="tr_i")
        transito_fim = c6.time_input("Fim", time(18, 30), key="tr_f")
        
        st.markdown("#### 💪 Treino")
        c7, c8 = st.columns(2)
        treino_inicio = c7.time_input("Início", time(19, 0), key="tre_i")
        treino_fim = c8.time_input("Fim", time(20, 0), key="tre_f")
        
        st.markdown("#### 📚 Estudo")
        c9, c10 = st.columns(2)
        estudo_inicio = c9.time_input("Início", time(20, 30), key="est_i")
        estudo_fim = c10.time_input("Fim", time(22, 0), key="est_f")
        
        st.divider()
        tempo_preparo = st.slider("⏱️ Tempo livre diário para cozinhar (minutos)", 0, 120, 30)
        
        if st.button("Salvar Agenda", use_container_width=True, type="primary"):
            st.session_state.cardapio_atual = None
            st.session_state.consumidos = set()
            st.success("Agenda salva! A IA agora conhece seus blocos de tempo.")

# --- ABA 2: ESTOQUE (Despensa) ---
with tab2:
    with st.container(border=True):
        st.subheader("Gerenciar Estoque")
        
        col_add, col_rem = st.columns(2)
        
        with col_add:
            with st.popover("➕ Novo Alimento", use_container_width=True):
                novo_nome = st.text_input("Nome")
                nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
                nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un", "dose"])
                novo_pronto = st.radio("Preparo Rápido/Consumo no Carro?", ["Não", "Sim"], horizontal=True)
                
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
    
    def formatar_estoque(row):
        if row["Quantidade"] <= 0:
            return "❌ ESGOTADO"
        return f"{row['Quantidade']} {row['Unidade']}"
        
    df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
    st.dataframe(df_visual[["Alimento", "Disponível", "Pronto/Rápido"]], use_container_width=True, hide_index=True)

# --- ABA 3: MOTOR DA IA (COM REGRAS DE TIME BLOCKING) ---
with tab3:
    st.info("A IA mapeará seus blocos ocupados e encaixará refeições nos espaços livres ou no trânsito.")
    st.write("") 
    
    if st.button("⚡ Gerar Cardápio Inteligente", use_container_width=True, type="primary"):
        if not api_configurada:
            st.error("Configure sua chave de API nos secrets.")
        else:
            with st.spinner("Mapeando blocos de tempo e calculando cardápio..."):
                despensa_ativa = st.session_state.despensa[st.session_state.despensa["Quantidade"] > 0]
                dados_despensa = despensa_ativa.to_dict(orient="records")
                
                prompt = f"""
                Você é um Nutricionista de Alta Performance especialista em 'Time Blocking' (Gestão de Tempo).
                Sua missão é criar um plano alimentar de 24h que se adapte CIRURGICAMENTE à agenda restrita do paciente.
                
                AGENDA DE BLOCOS OCUPADOS DO PACIENTE:
                - ☀️ Acorda às: {hora_acordar.strftime('%H:%M')} | 🌙 Dorme às: {hora_dormir.strftime('%H:%M')}
                - 💼 Bloco de Trabalho: {trab_inicio.strftime('%H:%M')} às {trab_fim.strftime('%H:%M')}
                - 🚗 Bloco de Trânsito: {transito_inicio.strftime('%H:%M')} às {transito_fim.strftime('%H:%M')}
                - 💪 Bloco de Treino: {treino_inicio.strftime('%H:%M')} às {treino_fim.strftime('%H:%M')}
                - 📚 Bloco de Estudo: {estudo_inicio.strftime('%H:%M')} às {estudo_fim.strftime('%H:%M')}
                - ⏱️ Tempo limite para cozinhar no dia inteiro: {tempo_preparo} min.
                
                REGRAS DE OURO DA LOGÍSTICA:
                1. Você NÃO PODE agendar preparos complexos durante os blocos de Trânsito, Treino ou Estudo.
                2. Use o Bloco de Trânsito ou pré-Treino APENAS para alimentos sinalizados como "Pronto/Rápido: Sim" no estoque (ex: Whey, Frutas, Barras). Especifique na instrução: "Consuma no carro/trânsito".
                3. Refeições que exigem fogão ou mastigação longa (almoço/jantar) devem estar no tempo LIVRE (antes de sair, pausa do trabalho, ou depois de chegar em casa).
                
                DESPENSA DISPONÍVEL (Estrito a isso): {dados_despensa}
                
                Retorne EXCLUSIVAMENTE em formato JSON puro. Estrutura:
                {{
                  "resumo_diario": {{ "calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g" }},
                  "refeicoes": [
                    {{ "hora": "HH:MM", "nome": "Nome do Prato", "ingredientes": "Qtd e Ingrediente", "instrucao_preparo": "Instrução de preparo E de logística (ex: 'Bata o whey antes de sair e tome durante o engarrafamento')", "macros": {{ "calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g" }}, "uso_despensa": [ {{ "nome_exato": "NOME EXATO", "qtd_descontada": 150 }} ] }}
                  ]
                }}
                """
                
                try:
                    resposta = modelo.generate_content(prompt)
                    texto_resposta = resposta.text.strip()
                    
                    match = re.search(r'\{.*\}', texto_resposta, re.DOTALL)
                    if match:
                        texto_limpo = match.group(0)
                    else:
                        texto_limpo = texto_resposta
                        
                    st.session_state.cardapio_atual = json.loads(texto_limpo)
                    st.session_state.consumidos = set()
                    st.rerun()
                    
                except Exception as e:
                    erro_str = str(e)
                    if "429" in erro_str or "Quota" in erro_str:
                        st.error("🚨 O Google bloqueou a geração por excesso de uso (Cota Esgotada). Crie uma nova chave API em um novo projeto no Google AI Studio.")
                    else:
                        st.error(f"🚨 Erro na IA: {erro_str}")

# --- ABA 4: PAINEL AO VIVO ---
with tab4:
    hora_agora = datetime.now(fuso_local).strftime("%H:%M")
    
    if st.session_state.cardapio_atual is None:
        st.warning("Gere a estratégia na aba 'Gerador' para acompanhar seu dia.")
    else:
        with st.container(border=True):
            st.markdown(f"### 🎯 Resumo do Dia (Agora: {hora_agora})")
            resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🔥 Kcal", resumo.get('calorias_totais', '0'))
            c2.metric("🥩 Prot", resumo.get('proteinas_totais', '0g'))
            c3.metric("🌾 Carb", resumo.get('carbos_totais', '0g'))
            c4.metric("🥑 Gord", resumo.get('gorduras_totais', '0g'))

        refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
        progresso = len(st.session_state.consumidos)
        total_refeicoes = len(refeicoes)
        
        st.progress(progresso / total_refeicoes if total_refeicoes > 0 else 0)
        
        for i, ref in enumerate(refeicoes):
            id_ref = f"ref_{i}"
            ja_consumido = id_ref in st.session_state.consumidos
            
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

# --- ABA 5: LISTA DE COMPRAS ---
with tab5:
    with st.container(border=True):
        st.markdown("### 🛒 Inteligência de Reposição")
        st.write("O NutryAi identificou que os seguintes itens acabaram no seu estoque:")
        
        estoque_zerado = st.session_state.despensa[st.session_state.despensa["Quantidade"] <= 0]
        
        if estoque_zerado.empty:
            st.success("Tudo certo por aqui! Seu estoque está abastecido para os próximos preparos. ✅")
        else:
            for index, row in estoque_zerado.iterrows():
                st.error(f"⚠️ **{row['Alimento']}** precisa ser reposto.")
                
    with st.container(border=True):
        st.markdown("### 📝 Bloco de Notas do Mercado")
        anotacoes = st.text_area("O que mais você precisa trazer?", height=120, placeholder="Ex: Temperos, papel toalha, café...")
        if st.button("Salvar Anotações Temporárias"):
            st.toast("Suas anotações ficarão na tela enquanto você estiver com o app aberto!")
