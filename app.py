import streamlit as st
import pandas as pd
from datetime import datetime, time

# Configuração da página
st.set_page_config(page_title="Minha Dieta IA", layout="wide")
st.title("🤖 Assistente de Nutrição Dinâmica")

# Criando as abas do aplicativo
tab1, tab2, tab3, tab4 = st.tabs(["🕒 Rotina de Hoje", "🛒 Despensa", "🧠 Gerador (IA)", "🔔 Notificações"])

# --- ABA 1: ROTINA DIÁRIA ---
with tab1:
    st.header("Como vai ser o seu dia hoje?")
    
    col1, col2 = st.columns(2)
    with col1:
        hora_acordar = st.time_input("Horário que acordou / vai acordar", time(6, 0))
        hora_dormir = st.time_input("Horário que pretende dormir", time(23, 0))
    with col2:
        trabalho_inicio = st.time_input("Início do expediente", time(8, 0))
        trabalho_fim = st.time_input("Fim do expediente", time(18, 0))
    
    tempo_preparo = st.slider("Tempo disponível para cozinhar hoje (minutos)", 0, 120, 20)
    
    if st.button("Salvar Rotina"):
        st.success("Rotina salva! Vá para o Gerador para criar o plano.")

# --- ABA 2: DESPENSA ---
with tab2:
    st.header("O que temos em casa?")
    
    # Banco de dados simulado da despensa atual
    if 'despensa' not in st.session_state:
        st.session_state.despensa = pd.DataFrame({
            "Alimento": ["Peito de Frango", "Arroz Branco", "Ovo", "Açaí (Zero Xarope)", "Whey Protein"],
            "Quantidade Disponível": ["500g", "1kg", "12 un", "400g", "900g"],
            "Pronto/Rápido": ["Não", "Não", "Sim", "Sim", "Sim"]
        })
    
    st.dataframe(st.session_state.despensa, use_container_width=True, hide_index=True)
    st.caption("No futuro, podemos adicionar um formulário aqui para você dar baixa no que acabou.")

# --- ABA 3: MOTOR DA IA ---
with tab3:
    st.header("Gerar Cardápio de 24h")
    st.write("A IA vai cruzar o seu tempo disponível com o que há na despensa.")
    
    if st.button("🧠 Gerar Estratégia do Dia"):
        with st.spinner("Analisando rotina e calculando macros..."):
            # Aqui é onde conectaremos a API da IA no futuro. 
            # Abaixo é a simulação do que a IA vai devolver.
            st.success("Estratégia calculada com base no seu dia!")
            
            st.markdown("""
            ### Cardápio Adaptado:
            * **Refeição 1 (06:30):** 3 Ovos mexidos + 1 Porção de Açaí (Preparo rápido de 5 min).
            * **Refeição 2 (12:00 - Levar para o trabalho):** 150g Frango + 100g Arroz. (Utilize seus 15 min restantes da manhã para montar a marmita).
            * **Refeição 3 (16:00 - No trabalho):** Dose de Whey Protein (Fácil transporte).
            """)

# --- ABA 4: NOTIFICAÇÕES (LEMBRETES) ---
with tab4:
    st.header("Lembretes Ativos")
    st.write("Estes são os gatilhos que o sistema enviará para o seu celular (via Telegram) para manter você na linha.")
    
    # Tabela estruturada focada apenas em ação, horário e instrução (sem campos desnecessários)
    lembretes = pd.DataFrame({
        "Ação": ["Preparar marmita", "Consumir Refeição 1", "Consumir Refeição 2", "Bater Ponto Nutricional"],
        "Horário": ["06:15", "06:30", "12:00", "16:00"],
        "Descrição": ["Fazer frango e arroz e guardar na bolsa", "Ovos e Açaí antes de sair", "Marmita de frango e arroz no trabalho", "Dose de Whey com água"]
    })
    
    st.table(lembretes)
