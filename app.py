import streamlit as st
import pandas as pd
from datetime import datetime, time
import google.generativeai as genai
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Minha Dieta IA", layout="wide")
st.title("🤖 Assistente de Nutrição Dinâmica")

# --- INICIALIZAÇÃO DE DADOS (MEMÓRIA DO APP) ---
if 'despensa' not in st.session_state:
    st.session_state.despensa = pd.DataFrame({
        "Alimento": ["Peito de Frango", "Arroz Branco", "Ovo", "Açaí (Zero Xarope)", "Whey Protein"],
        "Quantidade Disponível": ["500g", "1kg", "12 un", "400g", "900g"],
        "Pronto/Rápido": ["Não", "Não", "Sim", "Sim", "Sim"]
    })

if 'cardapio_atual' not in st.session_state:
    st.session_state.cardapio_atual = None

# --- CONFIGURAÇÃO DA API DA IA ---
CHAVE_API = "COLE_SUA_CHAVE_AQUI" 
genai.configure(api_key=CHAVE_API)
modelo = genai.GenerativeModel('gemini-2.5-flash')

# --- CRIANDO AS ABAS ---
tab1, tab2, tab3, tab4 = st.tabs(["🕒 Rotina de Hoje", "🛒 Despensa", "🧠 Gerador (IA)", "🔴 Painel ao Vivo"])

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
        st.success("Rotina salva! Vá para a aba Gerador para criar o plano.")

# --- ABA 2: DESPENSA ---
with tab2:
    st.header("O que temos em casa?")
    st.dataframe(st.session_state.despensa, use_container_width=True, hide_index=True)

# --- ABA 3: MOTOR DA IA ---
with tab3:
    st.header("Gerar Cardápio de 24h")
    
    if st.button("🧠 Gerar Estratégia do Dia"):
        if CHAVE_API == "COLE_SUA_CHAVE_AQUI":
            st.error("⚠️ Atenção: Coloque sua chave de API do Google AI Studio no código!")
        else:
            with st.spinner("Calculando sua logística alimentar..."):
                dados_despensa = st.session_state.despensa.to_dict(orient="records")
                
                prompt = f"""
                Você é um assistente de nutrição prático e focado em logística. 
                Monte um cardápio de 24h cobrindo as necessidades nutricionais básicas.
                
                MINHA ROTINA HOJE:
                - Acordo às: {hora_acordar.strftime('%H:%M')}
                - Durmo às: {hora_dormir.strftime('%H:%M')}
                - Trabalho das {trabalho_inicio.strftime('%H:%M')} às {trabalho_fim.strftime('%H:%M')}
                - Tempo para cozinhar hoje: {tempo_preparo} minutos. Se for pouco, priorize alimentos prontos ou marmitas rápidas.
                
                DESPENSA (Use apenas estes alimentos):
                {dados_despensa}
                
                Retorne EXCLUSIVAMENTE em formato JSON puro. O JSON deve conter uma lista "refeicoes", cada uma com: 
                "hora" (HH:MM), "nome", "ingredientes" e "instrucao_preparo".
                """
                
                try:
                    resposta = modelo.generate_content(prompt)
                    texto_resposta = resposta.text.strip()
                    if texto_resposta.startswith("```json"):
                        texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()
                    
                    st.session_state.cardapio_atual = json.loads(texto_resposta)
                    st.success("Plano gerado! Acompanhe seu progresso no 'Painel ao Vivo'.")
                            
                except Exception as e:
                    st.error(f"Erro ao processar a IA: {e}")

# --- ABA 4: PAINEL AO VIVO (NOVO FOCO) ---
with tab4:
    st.header("🔴 Acompanhamento do Dia")
    
    # Exibe a hora atual para o usuário se orientar
    hora_agora = datetime.now().strftime("%H:%M")
    st.subheader(f"Hora Atual: {hora_agora}")
    st.divider()

    if st.session_state.cardapio_atual is None:
        st.info("Gere a estratégia na aba 'Gerador' para iniciar o acompanhamento de hoje.")
    else:
        st.write("Marque as refeições conforme for consumindo para manter o controle da sua rotina.")
        
        # Cria um checklist interativo
        progresso = 0
        total_refeicoes = len(st.session_state.cardapio_atual.get("refeicoes", []))
        
        for i, ref in enumerate(st.session_state.cardapio_atual.get("refeicoes", [])):
            col_texto, col_check = st.columns([4, 1])
            
            with col_texto:
                st.markdown(f"### ⏰ {ref['hora']} - {ref['nome']}")
                st.write(f"**Prato:** {ref['ingredientes']}")
                st.caption(f"💡 {ref['instrucao_preparo']}")
            
            with col_check:
                # O Streamlit salva o estado do checkbox automaticamente usando a 'key'
                concluido = st.checkbox("Consumido", key=f"check_{i}")
                if concluido:
                    progresso += 1
            
            st.divider()
        
        # Barra de progresso visual no final
        st.write("### Progresso Diário")
        if total_refeicoes > 0:
            porcentagem = progresso / total_refeicoes
            st.progress(porcentagem)
            if porcentagem == 1.0:
                st.balloons()
                st.success("Parabéns! Você concluiu todas as metas do dia!")
