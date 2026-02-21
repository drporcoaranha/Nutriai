import streamlit as st
import pandas as pd
from datetime import time
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
# Substitua pela sua chave gratuita gerada no Google AI Studio
CHAVE_API = "COLE_SUA_CHAVE_AQUI" 
genai.configure(api_key=CHAVE_API)
modelo = genai.GenerativeModel('gemini-2.5-flash')

# --- CRIANDO AS ABAS ---
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
        st.success("Rotina salva! Vá para a aba Gerador para criar o plano.")

# --- ABA 2: DESPENSA ---
with tab2:
    st.header("O que temos em casa?")
    st.dataframe(st.session_state.despensa, use_container_width=True, hide_index=True)
    st.caption("Você pode editar esses dados conectando a uma planilha do Google futuramente.")

# --- ABA 3: MOTOR DA IA ---
with tab3:
    st.header("Gerar Cardápio de 24h")
    st.write("A IA vai cruzar o seu tempo disponível com o que há na despensa para montar a logística.")
    
    if st.button("🧠 Gerar Estratégia do Dia"):
        if CHAVE_API == "COLE_SUA_CHAVE_AQUI":
            st.error("⚠️ Atenção: Você precisa colocar sua chave de API no código na variável CHAVE_API!")
        else:
            with st.spinner("Analisando rotina, calculando macros e tempo de preparo..."):
                dados_despensa = st.session_state.despensa.to_dict(orient="records")
                
                prompt = f"""
                Você é um assistente de nutrição prático e focado em logística. 
                Monte um cardápio de 24h cobrindo as necessidades nutricionais básicas.
                
                MINHA ROTINA HOJE:
                - Acordo às: {hora_acordar.strftime('%H:%M')}
                - Durmo às: {hora_dormir.strftime('%H:%M')}
                - Trabalho das {trabalho_inicio.strftime('%H:%M')} às {trabalho_fim.strftime('%H:%M')}
                - Tempo que tenho para cozinhar hoje: {tempo_preparo} minutos. Se for pouco, priorize alimentos prontos, suplementos ou instrua a fazer marmitas rápidas.
                
                O QUE TENHO EM CASA (Despensa):
                {dados_despensa}
                
                REGRA DE OURO:
                Retorne a resposta EXCLUSIVAMENTE em formato JSON puro, sem marcações markdown. O JSON deve conter uma lista chamada "refeicoes", onde cada refeição tem: 
                "hora" (formato HH:MM), 
                "nome" (ex: Café da Manhã, Almoço no Trabalho), 
                "ingredientes" (com quantidades sugeridas), 
                "instrucao_preparo" (focado no tempo e se deve ser levado em marmita).
                """
                
                try:
                    resposta = modelo.generate_content(prompt)
                    texto_resposta = resposta.text.strip()
                    
                    # Tratamento caso a IA retorne com formatação de código
                    if texto_resposta.startswith("```json"):
                        texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()
                    
                    cardapio_gerado = json.loads(texto_resposta)
                    st.session_state.cardapio_atual = cardapio_gerado
                    
                    st.success("Estratégia calculada com sucesso!")
                    
                    # Renderiza o cardápio na tela
                    for ref in cardapio_gerado.get("refeicoes", []):
                        with st.expander(f"⏰ {ref['hora']} - {ref['nome']}", expanded=True):
                            st.write(f"**Ingredientes:** {ref['ingredientes']}")
                            st.info(f"💡 **Preparo/Logística:** {ref['instrucao_preparo']}")
                            
                except Exception as e:
                    st.error(f"Erro ao processar a resposta da IA. Detalhes: {e}")

# --- ABA 4: NOTIFICAÇÕES (LEMBRETES) ---
with tab4:
    st.header("Lembretes Ativos")
    
    if st.session_state.cardapio_atual is None:
        st.warning("Gere a estratégia do dia na aba 'Gerador' primeiro para visualizar os lembretes.")
    else:
        st.write("Estes são os gatilhos gerados automaticamente baseados na sua estratégia de hoje:")
        
        # Extraindo dados do JSON gerado para montar a tabela de lembretes
        lista_lembretes = []
        for ref in st.session_state.cardapio_atual.get("refeicoes", []):
            lista_lembretes.append({
                "Ação": f"Consumir: {ref['nome']}",
                "Horário": ref['hora'],
                "Instrução": ref['ingredientes']
            })
            
        df_lembretes = pd.DataFrame(lista_lembretes)
        st.table(df_lembretes)
        
        st.info("Próximo passo: Conectar estes horários ao envio de mensagens via Telegram.")
