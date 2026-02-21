import streamlit as st
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import google.generativeai as genai
import json
import os # NOVO: Biblioteca para lidar com arquivos do sistema

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Minha Dieta IA", layout="wide")
st.title("🤖 Assistente de Nutrição Dinâmica")

# --- FUNÇÕES DE MEMÓRIA PERMANENTE (NOVO) ---
ARQUIVO_DESPENSA = "despensa.csv"

def carregar_despensa():
    # Se o arquivo já existe (você já usou o app antes), ele carrega de lá
    if os.path.exists(ARQUIVO_DESPENSA):
        return pd.read_csv(ARQUIVO_DESPENSA)
    else:
        # Se for a primeira vez, ele cria a base e já salva
        df = pd.DataFrame({
            "Alimento": ["Peito de Frango", "Arroz Branco", "Ovo", "Açaí (Zero Xarope)", "Whey Protein", "Azeite"],
            "Quantidade": [500.0, 1000.0, 12.0, 400.0, 900.0, 1.0],
            "Unidade": ["g", "g", "un", "g", "g", "vidro"],
            "Pronto/Rápido": ["Não", "Não", "Sim", "Sim", "Sim", "Sim"]
        })
        df.to_csv(ARQUIVO_DESPENSA, index=False)
        return df

def salvar_despensa(df):
    # Grava as mudanças no arquivo permanentemente
    df.to_csv(ARQUIVO_DESPENSA, index=False)

# --- VERIFICAÇÃO SEGURA DA CHAVE DE API ---
api_configurada = False
if "GEMINI_API_KEY" in st.secrets:
    try:
        CHAVE_API = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=CHAVE_API)
        modelo = genai.GenerativeModel('gemini-2.5-flash')
        api_configurada = True
    except Exception as e:
        st.error(f"⚠️ Erro ao configurar a IA: {e}")
else:
    st.error("⚠️ ALERTA: A chave da API não foi encontrada no ambiente online!")

# --- AJUSTE DE FUSO HORÁRIO ---
fuso_local = timezone(timedelta(hours=-3))

# --- INICIALIZAÇÃO DE DADOS ---
if 'despensa' not in st.session_state:
    st.session_state.despensa = carregar_despensa() # Agora puxa do arquivo permanente!

if 'cardapio_atual' not in st.session_state:
    st.session_state.cardapio_atual = None

if 'consumidos' not in st.session_state:
    st.session_state.consumidos = set()

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
        st.session_state.cardapio_atual = None
        st.session_state.consumidos = set()
        st.success("Rotina salva! Vá para a aba Gerador para criar o plano.")

# --- ABA 2: DESPENSA (COM OPÇÃO DE REMOVER) ---
with tab2:
    st.header("Estoque da Casa")
    
    col_add, col_rem = st.columns(2)
    
    with col_add:
        with st.expander("➕ Adicionar Alimento", expanded=False):
            with st.form("form_novo_alimento"):
                novo_nome = st.text_input("Nome do Alimento")
                nova_qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
                nova_unidade = st.selectbox("Unidade", ["g", "kg", "ml", "L", "un", "pacote", "vidro"])
                novo_pronto = st.radio("Pronto/Rápido?", ["Não", "Sim"])
                
                if st.form_submit_button("Salvar no Estoque"):
                    if novo_nome:
                        novo_item = pd.DataFrame({
                            "Alimento": [novo_nome],
                            "Quantidade": [nova_qtd],
                            "Unidade": [nova_unidade],
                            "Pronto/Rápido": [novo_pronto]
                        })
                        st.session_state.despensa = pd.concat([st.session_state.despensa, novo_item], ignore_index=True)
                        salvar_despensa(st.session_state.despensa) # Salva no CSV
                        st.success(f"{novo_nome} adicionado!")
                        st.rerun()
                    else:
                        st.error("Preencha o nome!")

    # NOVO: Ferramenta para remover itens indesejados
    with col_rem:
        with st.expander("🗑️ Remover Alimento", expanded=False):
            lista_alimentos = st.session_state.despensa["Alimento"].tolist()
            item_remover = st.selectbox("Selecione o que acabou/está errado:", lista_alimentos)
            
            if st.button("Remover Permanentemente"):
                # Filtra a tabela mantendo apenas os itens diferentes do selecionado
                st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                salvar_despensa(st.session_state.despensa) # Salva no CSV
                st.success(f"{item_remover} removido!")
                st.rerun()

    st.write("### Itens Disponíveis")
    df_visual = st.session_state.despensa.copy()
    df_visual["Estoque"] = df_visual["Quantidade"].astype(str) + " " + df_visual["Unidade"]
    st.dataframe(df_visual[["Alimento", "Estoque", "Pronto/Rápido"]], use_container_width=True, hide_index=True)

# --- ABA 3: MOTOR DA IA ---
with tab3:
    st.header("Gerar Cardápio de 24h")
    
    if st.button("🧠 Gerar Estratégia do Dia"):
        if not api_configurada:
            st.error("⚠️ Configure sua chave de API nos secrets.")
        else:
            with st.spinner("Calculando logística, macros e cruzando com o estoque..."):
                dados_despensa = st.session_state.despensa.to_dict(orient="records")
                
                prompt = f"""
                Você é um nutricionista clínico e assistente de logística. 
                Monte um cardápio de 24h.
                
                ROTINA:
                - Acordo às: {hora_acordar.strftime('%H:%M')} | Durmo às: {hora_dormir.strftime('%H:%M')}
                - Trabalho das {trabalho_inicio.strftime('%H:%M')} às {trabalho_fim.strftime('%H:%M')}
                - Tempo para cozinhar hoje: {tempo_preparo} min.
                
                DESPENSA DISPONÍVEL (Use estritamente estes alimentos e respeite as quantidades máximas):
                {dados_despensa}
                
                Retorne EXCLUSIVAMENTE em formato JSON puro. Estrutura exata:
                {{
                  "resumo_diario": {{
                    "calorias_totais": 0, "proteinas_totais": "0g", "carbos_totais": "0g", "gorduras_totais": "0g"
                  }},
                  "refeicoes": [
                    {{
                      "hora": "HH:MM",
                      "nome": "Nome",
                      "ingredientes": "Qtd e Ingrediente",
                      "instrucao_preparo": "Instrução breve",
                      "macros": {{ "calorias": 0, "proteinas": "0g", "carbos": "0g", "gorduras": "0g" }},
                      "uso_despensa": [
                        {{ "nome_exato": "NOME EXATO DA DESPENSA", "qtd_descontada": 150 }}
                      ]
                    }}
                  ]
                }}
                """
                
                try:
                    resposta = modelo.generate_content(prompt)
                    texto_resposta = resposta.text.strip()
                    if texto_resposta.startswith("```json"):
                        texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()
                    
                    st.session_state.cardapio_atual = json.loads(texto_resposta)
                    st.session_state.consumidos = set()
                    st.success("Plano gerado! Acompanhe e dê baixa no 'Painel ao Vivo'.")
                            
                except Exception as e:
                    st.error("Erro ao processar a IA. Tente clicar em Gerar novamente.")

# --- ABA 4: PAINEL AO VIVO ---
with tab4:
    st.header("🔴 Acompanhamento do Dia")
    
    hora_agora = datetime.now(fuso_local).strftime("%H:%M")
    st.subheader(f"Hora Atual: {hora_agora}")
    
    if st.session_state.cardapio_atual is None:
        st.info("Gere a estratégia na aba 'Gerador' para iniciar o acompanhamento.")
    else:
        resumo = st.session_state.cardapio_atual.get("resumo_diario", {})
        st.markdown("### 📊 Meta Nutricional")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Calorias", resumo.get('calorias_totais', '0'))
        col_m2.metric("Proteínas", resumo.get('proteinas_totais', '0g'))
        col_m3.metric("Carboidratos", resumo.get('carbos_totais', '0g'))
        col_m4.metric("Gorduras", resumo.get('gorduras_totais', '0g'))
        st.divider()

        refeicoes = st.session_state.cardapio_atual.get("refeicoes", [])
        progresso = len(st.session_state.consumidos)
        total_refeicoes = len(refeicoes)
        
        for i, ref in enumerate(refeicoes):
            col_texto, col_check = st.columns([4, 1])
            id_ref = f"ref_{i}"
            
            with col_texto:
                st.markdown(f"#### ⏰ {ref['hora']} - {ref['nome']}")
                st.write(f"**Prato:** {ref['ingredientes']}")
                macros = ref.get('macros', {})
                st.caption(f"🔥 {macros.get('calorias', 0)} kcal | 🥩 Prot: {macros.get('proteinas', '0g')} | 🌾 Carb: {macros.get('carbos', '0g')} | 🥑 Gord: {macros.get('gorduras', '0g')}")
            
            with col_check:
                ja_consumido = id_ref in st.session_state.consumidos
                concluido = st.checkbox("Consumido", key=f"check_{i}", value=ja_consumido, disabled=ja_consumido)
                
                if concluido and not ja_consumido:
                    st.session_state.consumidos.add(id_ref)
                    
                    for item_usado in ref.get("uso_despensa", []):
                        nome_exato = item_usado.get("nome_exato")
                        qtd_descontar = item_usado.get("qtd_descontada", 0)
                        
                        idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == nome_exato].tolist()
                        if idx:
                            linha = idx[0]
                            st.session_state.despensa.at[linha, 'Quantidade'] -= float(qtd_descontar)
                    
                    salvar_despensa(st.session_state.despensa) # NOVO: Salva no CSV após consumir
                    st.rerun() 
            
            st.divider()
        
        if total_refeicoes > 0:
            porcentagem = len(st.session_state.consumidos) / total_refeicoes
            st.progress(porcentagem)
            if porcentagem == 1.0:
                st.balloons()
                st.success("Dia finalizado! Seus macros e seu estoque estão atualizados.")
