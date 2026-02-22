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
st.caption("Seu assistente de nutrição flexível, gestão de tempo e controle glicêmico.")

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🕒 Agenda", "📦 Estoque", "🧠 Dia a Dia", "👩‍⚕️ Plano", "💬 Chat", "🔴 Ao Vivo", "🛒 Compras"])

# --- ABA 1: ROTINA EM BLOCOS DE TEMPO ---
with tab1:
    with st.container(border=True):
        st.subheader("Blocos de Tempo Ocupado")
        
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
            st.session_state.cardapio_ideal = None 
            st.session_state.consumidos = set()
            st.success("Agenda salva! A IA agora conhece seus blocos de tempo.")

# --- ABA 2: ESTOQUE (Despensa) ---
with tab2:
    with st.container(border=True):
        st.subheader("Gerenciar Estoque")
        col_add, col_rem = st.columns(2)
        
        with col_add:
            with st.popover("➕ Novo", use_container_width=True):
                novo_nome = st.text_input("Nome")
                nova_qtd = st.number_input("Qtd", min_value=0.0, step=1.0)
                nova_unidade = st.selectbox("Medida", ["g", "kg", "ml", "L", "un", "dose", "colher"])
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
                item_remover = st.selectbox("Apagar:", lista_alimentos)
                if st.button("Excluir"):
                    st.session_state.despensa = st.session_state.despensa[st.session_state.despensa["Alimento"] != item_remover]
                    salvar_despensa(st.session_state.despensa)
                    st.rerun()

    df_visual = st.session_state.despensa.copy()
    def formatar_estoque(row):
        return "❌ ESGOTADO" if row["Quantidade"] <= 0 else f"{row['Quantidade']} {row['Unidade']}"
    df_visual["Disponível"] = df_visual.apply(formatar_estoque, axis=1)
    st.dataframe(df_visual[["Alimento", "Disponível", "Pronto/Rápido"]], use_container_width=True, hide_index=True)

# --- ABA 3: MOTOR DA IA (CENÁRIO REAL / DIA A DIA) ---
with tab3:
    st.info("A IA vai cruzar seus horários com o que você **TEM HOJE NO ESTOQUE**.")
    if st.button("⚡ Gerar Cardápio Baseado no Estoque", use_container_width=True, type="primary"):
        if not api_configurada:
            st.error("Configure sua chave de API nos secrets.")
        else:
            with st.spinner("Analisando estoque e calculando sinergia..."):
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
                    st.rerun()
                except Exception as e:
                    st.error(f"🚨 Erro na IA: {e}")

# --- ABA 4: A NOVA CONSULTA (METAS DE MACROS FLEXÍVEIS) ---
with tab4:
    st.info("A Nutricionista definiu **Metas de Macros** e **Porções Flexíveis** para a sua rotina ideal.")
    if st.button("👩‍⚕️ Gerar Estratégia Flexível", use_container_width=True):
        if not api_configurada:
            st.error("Configure API nos secrets.")
        else:
            with st.spinner("Calculando distribuição de macros..."):
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
                except Exception as e:
                    st.error(f"🚨 Erro na IA: {e}")
                    
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
                st.markdown(f"#### ⏰ {ref_ideal.get('hora', '')} - {ref_ideal.get('nome', '')} ({ref_ideal.get('alvo_macros', '')})")
                st.markdown(f"**🧩 Montagem:** {ref_ideal.get('estrutura_prato', '')}")
                st.markdown(f"**💡 Opções:** {ref_ideal.get('sugestoes_flexiveis', '')}")
                st.info(f"👩‍⚕️ **Clínica:** {ref_ideal.get('instrucao_clinica', '')}")

# --- ABA 5: CHAT COM A NUTRICIONISTA ---
with tab5:
    st.markdown("### 💬 Nutri de Bolso 24h")
    st.write("Tire dúvidas sobre alimentos, peça para substituir uma refeição ou **envie a foto do seu prato** para avaliação de macros e insulina.")

    # Uploader de foto do prato
    foto_upload = st.file_uploader("📸 Enviar foto do prato ou rótulo", type=["jpg", "jpeg", "png"])

    # Exibe o histórico de conversa na tela (apenas textos para otimizar memória)
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Caixa de texto de envio (CORRIGIDO: O Python exige que a atribuição e o "if" sejam separados)
    prompt_chat = st.chat_input("Ex: Nutri, avalie esse prato que peguei no restaurante...")
    
    if prompt_chat:
        if not api_configurada:
            st.error("Configure sua chave de API nos secrets.")
        else:
            # Mostra a mensagem do usuário na hora e salva no histórico
            st.session_state.chat_history.append({"role": "user", "content": prompt_chat})
            with st.chat_message("user"):
                st.markdown(prompt_chat)
                if foto_upload:
                    st.image(foto_upload, width=250)
                    st.caption("Imagem enviada para análise.")

            # Prepara a IA e gera a resposta
            with st.chat_message("assistant"):
                with st.spinner("A Nutri está digitando..."):
                    try:
                        # Contexto mestre para a IA agir como a Nutri do App
                        conteudo_ia = [
                            "Você é a NutryAi, uma Nutricionista Clínica empática, direta e especialista em Resistência à Insulina e Dieta Flexível. Seja prestativa, use um tom motivador e direto ao ponto. Se o paciente enviar uma imagem, analise os alimentos visíveis, estime calorias, liste os macros por cima e diga se o prato favorece picos de insulina (orientando correções rápidas, como adicionar mais salada ou azeite).",
                            prompt_chat
                        ]
                        
                        # Se tiver foto anexada, processa com o Pillow e manda pra IA
                        if foto_upload:
                            imagem_pil = Image.open(foto_upload)
                            conteudo_ia.append(imagem_pil)

                        resposta_chat = modelo.generate_content(conteudo_ia)
                        st.markdown(resposta_chat.text)
                        
                        # Salva a resposta da Nutri no histórico
                        st.session_state.chat_history.append({"role": "assistant", "content": resposta_chat.text})
                    
                    except Exception as e:
                        st.error(f"Erro ao falar com a Nutri: {e}")

# --- ABA 6: PAINEL AO VIVO ---
with tab6:
    hora_agora = datetime.now(fuso_local).strftime("%H:%M")
    if st.session_state.cardapio_atual is None:
        st.warning("Vá na aba '🧠 Dia a Dia' para gerar seu cardápio com base no que você já tem em casa.")
    else:
        with st.container(border=True):
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
                with col_check:
                    concluido = st.checkbox("Baixa", key=f"check_{i}", value=ja_consumido, disabled=ja_consumido)
                    if concluido and not ja_consumido:
                        st.session_state.consumidos.add(id_ref)
                        for item in ref.get("uso_despensa", []):
                            idx = st.session_state.despensa.index[st.session_state.despensa['Alimento'] == item.get("nome_exato")].tolist()
                            if idx: st.session_state.despensa.at[idx[0], 'Quantidade'] -= float(item.get("qtd_descontada", 0))
                        salvar_despensa(st.session_state.despensa)
                        st.rerun()

# --- ABA 7: LISTA DE COMPRAS ---
with tab7:
    with st.container(border=True):
        st.markdown("### 🛒 Inteligência de Reposição")
        estoque_zerado = st.session_state.despensa[st.session_state.despensa["Quantidade"] <= 0]
        if estoque_zerado.empty:
            st.success("Tudo certo por aqui! Seu estoque está abastecido. ✅")
        else:
            for index, row in estoque_zerado.iterrows():
                st.error(f"⚠️ **{row['Alimento']}** precisa ser reposto.")
    with st.container(border=True):
        st.text_area("O que mais a 'Nutricionista Ideal' sugeriu comprar?", height=120)
        if st.button("Salvar Anotações Temporárias"): st.toast("Anotado!")

