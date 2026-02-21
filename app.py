import streamlit as st
import google.generativeai as genai
import pandas as pd
import os
from datetime import datetime
import re
import random
import io

# --- CONFIGURAÇÃO DA CHAVE DE API (SEGURA) ---
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=API_KEY)
    CONEXAO_OK = True
except:
    API_KEY = ""
    CONEXAO_OK = False

# --- Configuração da Página ---
st.set_page_config(
    page_title="Coach Suprabio",
    page_icon="🏆",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- CSS Responsivo e Estilo do Chat ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        height: 3.5em;
        font-weight: bold;
        border-radius: 12px;
        font-size: 15px;
    }
    .cliente-box {
        padding: 15px;
        border-radius: 10px;
        background-color: #f0f2f6;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    .vendedor-box {
        padding: 15px;
        border-radius: 10px;
        background-color: #e8f4f8;
        border-right: 5px solid #0088cc;
        margin-bottom: 10px;
        text-align: right;
    }
    .chat-texto {
        font-size: 17px;
        color: #31333F;
    }
    .chat-label {
        font-size: 12px;
        font-weight: bold;
        color: #777;
        margin-bottom: 5px;
    }
    /* Classe para centralizar títulos */
    .titulo-central {
        text-align: center;
        font-size: 2.2em;
        font-weight: 800;
        margin-bottom: 5px;
    }
    .subtitulo-central {
        text-align: center;
        color: #555;
        margin-bottom: 20px;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- ARQUIVOS ---
ARQUIVO_HISTORICO = "historico_treinamento.xlsx"
ARQUIVO_EQUIPE = "equipe.csv"

# --- BANCO DE DADOS DE CASOS REAIS (49 SITUAÇÕES) ---
CASOS_REAIS = [
    {"queixa": "Moça, eu ando muito esquecido, a cabeça parece que não funciona direito e tô sem energia mental.", "produto_alvo": "Magnésio Dimalato ou Complexo B"},
    {"queixa": "Sinto muitas cãibras na panturrilha de madrugada, acordo gemendo de dor. Tem alguma vitamina pra isso?", "produto_alvo": "Magnésio Dimalato ou Cloreto de Magnésio"},
    {"queixa": "Acordo de manhã e parece que passou um caminhão em cima de mim. O corpo todo dolorido, pesado, uma canseira muscular crônica.", "produto_alvo": "Magnésio Dimalato"},
    {"queixa": "Tenho sentido muita dor nas articulações, meu joelho estala quando subo escada. Tem algo pra 'lubrificar'?", "produto_alvo": "Cloreto de Magnésio ou Colágeno"},
    {"queixa": "Tenho uns bicos de papagaio na coluna e acordo com as juntas todas travadas, duro igual um robô.", "produto_alvo": "Cloreto de Magnésio"},
    {"queixa": "Tenho um esporão no calcanhar que me mata de dor quando piso no chão de manhã. Me falaram de um suplemento que desfaz isso.", "produto_alvo": "Cloreto de Magnésio"},
    {"queixa": "Eu deito na cama e fico rolando. O corpo cansa, mas a mente não desliga. Queria algo natural pra dormir.", "produto_alvo": "Melatonina ou Clamvit Zen"},
    {"queixa": "Eu viajo muito a trabalho e meu fuso horário vira uma bagunça, perco totalmente a hora de dormir.", "produto_alvo": "Melatonina"},
    {"queixa": "Eu até pego no sono rápido, mas acordo umas 3 da manhã e fico com o olho arregalado até clarear o dia. Tô um zumbi.", "produto_alvo": "Melatonina"},
    {"queixa": "Trabalho por turno, uma semana de dia, outra de madrugada. Meu relógio biológico pifou, não durmo direito em horário nenhum.", "produto_alvo": "Melatonina"},
    {"queixa": "Tô sentindo uma fraqueza no coração, me sinto muito cansado depois que fiz 40 anos. O médico falou de uma vitamina pro coração.", "produto_alvo": "Coenzima Q10"},
    {"queixa": "Comecei a tomar estatina pra colesterol e agora sinto muita dor muscular, parece que fui atropelado. O médico falou de um suplemento.", "produto_alvo": "Coenzima Q10"},
    {"queixa": "Tenho muita enxaqueca e o médico disse que tem um suplemento que dá energia para as células e ajuda a diminuir as crises.", "produto_alvo": "Coenzima Q10"},
    {"queixa": "Tive uma infecção forte há uns meses e parece que minha bateria nunca mais voltou aos 100%. Qualquer esforço já me deixa ofegante.", "produto_alvo": "Coenzima Q10"},
    {"queixa": "Sinto um formigamento constante nas mãos e nos pés, além de um cansaço que não passa com nada.", "produto_alvo": "Complexo B"},
    {"queixa": "Sou diabético e ultimamente tenho sentido umas pontadas e uma queimação esquisita na sola dos pés.", "produto_alvo": "Complexo B"},
    {"queixa": "Tô bebendo muita bebida alcoólica nos finais de semana e sinto que meu fígado e meus nervos tão pedindo arrego.", "produto_alvo": "Complexo B"},
    {"queixa": "Minha boca tá cheia de afta e eu pego resfriado toda semana. Minha imunidade deve estar no chão.", "produto_alvo": "Vitamina C ou Suprabio A-Z"},
    {"queixa": "Meu nariz vive escorrendo. Basta o tempo mudar um pouquinho ou bater um vento gelado que eu já fico resfriada.", "produto_alvo": "Vitamina C"},
    {"queixa": "Sinto que minha garganta arranha por qualquer friagem. E também demora muito pra cicatrizar qualquer machucadinho.", "produto_alvo": "Vitamina C"},
    {"queixa": "O médico mandou eu baixar meu triglicerídeos e colesterol ruim, mas queria algo pra ajudar junto com a dieta.", "produto_alvo": "Ômega 3"},
    {"queixa": "Minha memória tá terrível, esqueço onde coloquei a chave, o que ia falar... Queria algo pro cérebro e que fizesse bem pro coração.", "produto_alvo": "Ômega 3"},
    {"queixa": "Vou prestar concurso no fim do ano, mas sento pra estudar e não consigo focar, parece que dá um branco. Falaram que gordura de peixe é bom.", "produto_alvo": "Ômega 3"},
    {"queixa": "Tô me sentindo fraco, sem disposição pra trabalhar. Sou homem, tenho 35 anos, queria um tônico geral.", "produto_alvo": "Suprabio Homem"},
    {"queixa": "Trabalho o dia inteiro sentado no computador, chego em casa exausto, sem pique nem pra brincar com meus filhos.", "produto_alvo": "Suprabio Homem"},
    {"queixa": "A rotina tá tão puxada que chego à noite em casa sem vontade de nada, até minha libido caiu por falta de ânimo físico.", "produto_alvo": "Suprabio Homem"},
    {"queixa": "Menina, tô na menopausa, sentindo uns calores e muito desânimo. Tem alguma vitamina completa pra mulher?", "produto_alvo": "Suprabio Mulher"},
    {"queixa": "Meu fluxo menstrual é muito intenso e depois eu fico uns dias me arrastando, pálida e sem força nenhuma.", "produto_alvo": "Suprabio Mulher ou Complexo B"},
    {"queixa": "Trabalho, cuido da casa, dos filhos... tô me sentindo esgotada fisicamente e com a pele meio sem vida.", "produto_alvo": "Suprabio Mulher"},
    {"queixa": "Já passei dos 50 anos e sinto que meus ossos estão fracos e me falta energia pro dia a dia.", "produto_alvo": "Suprabio 50+"},
    {"queixa": "Minha mãe tem 68 anos e está comendo muito mal. Quase não come carne e tá ficando muito fraquinha.", "produto_alvo": "Suprabio 50+"},
    {"queixa": "Meu pai tá com 75 anos, almoça que é um passarinho. Tô com medo dele ficar desnutrido ou perder músculo.", "produto_alvo": "Suprabio 50+"},
    {"queixa": "Olha o estado da minha unha! Tá quebrando igual papel. E meu cabelo cai muito no banho.", "produto_alvo": "Suprabio Cabelos e Unhas"},
    {"queixa": "Tirei aquele alongamento de gel e minha unha natural tá um papel, quebra só de encostar. Preciso fortalecer urgente.", "produto_alvo": "Suprabio Cabelos e Unhas"},
    {"queixa": "Tive dengue faz uns meses e agora meu cabelo tá caindo aos tufos, tô ficando desesperada.", "produto_alvo": "Suprabio Cabelos e Unhas"},
    {"queixa": "Meu intestino é um relógio... parado! Fico 3 dias sem ir ao banheiro e me sinto inchada.", "produto_alvo": "Fibras ou Lactulose"},
    {"queixa": "Tenho hemorroida e sofro demais pra ir ao banheiro porque as fezes ficam muito ressecadas. Preciso amolecer isso urgente.", "produto_alvo": "Lactulose ou Fibras"},
    {"queixa": "Eu não quero tomar purgante porque me dá cólica, mas minha barriga tá tão estufada que não fecha nem a calça. Queria algo natural pra uso diário.", "produto_alvo": "Fibras"},
    {"queixa": "Minha avó é acamada e o intestino dela é super preguiçoso. O médico falou de um xarope doce que não agride o estômago.", "produto_alvo": "Lactulose"},
    {"queixa": "Toda tarde minha visão fica cansada, embaçada, parece que forço muito pra ler.", "produto_alvo": "Luteína"},
    {"queixa": "Fico o dia todo olhando pra tela do computador e do celular. No final do dia meu olho arde muito e fica seco.", "produto_alvo": "Luteína"},
    {"queixa": "Trabalho como motorista de aplicativo, rodo o dia todo. A claridade do sol e farol à noite tão me incomodando demais.", "produto_alvo": "Luteína"},
    {"queixa": "Fiz um exame e deu osteopenia. O médico mandou tomar cálcio, mas disseram que tem um que vai direto pro osso.", "produto_alvo": "Cálcio MDK"},
    {"queixa": "As mulheres da minha família têm histórico de osteoporose. Eu já passei dos 40 e queria começar a prevenir desde já.", "produto_alvo": "Cálcio MDK"},
    {"queixa": "Tomei um tombo bobo e trinquei o osso do braço. Queria um suplemento pra ajudar a colar esse osso mais rápido e fortificar.", "produto_alvo": "Cálcio MDK"},
    {"queixa": "Estou sentindo minha pele do rosto e dos braços muito flácida, perdendo a firmeza da juventude.", "produto_alvo": "Colágeno"},
    {"queixa": "Emagreci bastante nos últimos meses, mas agora tô sentindo a pele do rosto meio caída, sabe? Queria algo de dentro pra fora.", "produto_alvo": "Colágeno"},
    {"queixa": "Tô muito estressado, pavio curto, qualquer coisa eu explodo. Queria algo pra acalmar sem dar sono.", "produto_alvo": "Clamvit Zen"},
    {"queixa": "Estou numa ansiedade terrível por conta de problemas na família. Meu coração até acelera, mas tenho pavor de tomar tarja preta.", "produto_alvo": "Clamvit Zen"},
    {"queixa": "Tenho sentido um aperto no peito e um nó na garganta de tanta ansiedade com as provas da faculdade, mas não posso tomar remédio que dopa.", "produto_alvo": "Clamvit Zen"}
]

# --- FUNÇÕES ---
def carregar_equipe():
    if os.path.exists(ARQUIVO_EQUIPE):
        try: return pd.read_csv(ARQUIVO_EQUIPE)['Nome'].tolist()
        except: pass
    padrao = ["André", "Bruna", "Eliana", "Leticia", "Marcella", "Jessica", "Diego", "Anderson"]
    salvar_equipe(padrao)
    return padrao

def salvar_equipe(lista):
    pd.DataFrame({'Nome': lista}).to_csv(ARQUIVO_EQUIPE, index=False)

def carregar_historico():
    if os.path.exists(ARQUIVO_HISTORICO):
        try: return pd.read_excel(ARQUIVO_HISTORICO)
        except: pass
    return pd.DataFrame(columns=["Data", "Colaborador", "ProdutoAlvo", "Conversa", "Nota", "FeedbackIA"])

def salvar_sessao(dados):
    df = carregar_historico()
    df = pd.concat([df, pd.DataFrame([dados])], ignore_index=True)
    df.to_excel(ARQUIVO_HISTORICO, index=False)

@st.cache_resource
def encontrar_modelo():
    if not API_KEY: return None
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not modelos: return "models/gemini-pro"
        for m in modelos:
            if "flash" in m: return m
        return modelos[0]
    except: return None

MODELO_NOME = encontrar_modelo()

# --- ESTADO INICIAL ---
if "equipe" not in st.session_state: st.session_state.equipe = carregar_equipe()
if "historico_chat" not in st.session_state: st.session_state.historico_chat = []
if "turno" not in st.session_state: st.session_state.turno = 1
if "produto_alvo" not in st.session_state: st.session_state.produto_alvo = ""
if "nota" not in st.session_state: st.session_state.nota = 0.0
if "feedback" not in st.session_state: st.session_state.feedback = ""

# ==========================================
# HEADER CENTRALIZADO E SIMÉTRICO
# ==========================================
st.markdown("<div class='titulo-central'>🏆 💊 Coach Suprabio 🧠</div>", unsafe_allow_html=True)

if not CONEXAO_OK:
    st.error("⚠️ Configure a API Key nos 'Secrets'!")

# Botão de configurações centralizado em 3 colunas para simetria
col_esq, col_meio, col_dir = st.columns([1, 1, 1])
with col_meio:
    with st.popover("⚙️ Ajustes", use_container_width=True):
        st.header("Ajustes do Gerente")
        if not CONEXAO_OK:
            nova_key = st.text_input("Cole API Key aqui:", type="password")
            if nova_key:
                genai.configure(api_key=nova_key)
                st.rerun()
                
        novo = st.text_input("Add Colaborador:")
        if st.button("➕ Adicionar") and novo:
            st.session_state.equipe.append(novo)
            salvar_equipe(st.session_state.equipe)
            st.rerun()
            
        df_historico = carregar_historico()
        if not df_historico.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_historico.to_excel(writer, index=False, sheet_name='Treinamentos')
            
            st.download_button(
                label="📥 Baixar Excel",
                data=buffer.getvalue(),
                file_name=f"treino_coach_suprabio_{datetime.now().strftime('%d%m')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

st.markdown("---")
# ==========================================

# Subtítulo Centralizado
st.markdown("<h3 class='subtitulo-central'>👤 Quem vai treinar agora?</h3>", unsafe_allow_html=True)
colaborador = st.selectbox("Vendedor:", ["Clique aqui para selecionar..."] + st.session_state.equipe, label_visibility="collapsed")
st.markdown("<br>", unsafe_allow_html=True)

if colaborador != "Clique aqui para selecionar...":
    
    if not st.session_state.historico_chat:
        if st.button("🔔 CHAMAR PRÓXIMO CLIENTE", type="primary"):
            caso = random.choice(CASOS_REAIS)
            st.session_state.historico_chat = [{"role": "Cliente", "text": caso["queixa"]}]
            st.session_state.produto_alvo = caso["produto_alvo"]
            st.session_state.turno = 1
            st.session_state.feedback = ""
            st.rerun()

    else:
        for msg in st.session_state.historico_chat:
            if msg["role"] == "Cliente":
                st.markdown(f"""<div class="cliente-box"><div class="chat-label">🗣️ CLIENTE:</div><div class="chat-texto">"{msg['text']}"</div></div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="vendedor-box"><div class="chat-label">🧑‍⚕️ {colaborador.upper()}:</div><div class="chat-texto">{msg['text']}</div></div>""", unsafe_allow_html=True)

        if not st.session_state.feedback:
            
            with st.expander("🤫 Gabarito do Gerente (Não mostre ao colaborador)"):
                st.write(f"**Indicação ideal esperada:** {st.session_state.produto_alvo}")
                
            st.write(f"*(Turno {st.session_state.turno} de 3)*")
            resposta = st.text_area("✍️ O que você diz para o cliente?", height=80, key=f"input_{st.session_state.turno}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.session_state.turno < 3:
                    if st.button("🗣️ RESPONDER E CONTINUAR"):
                        if not resposta:
                            st.warning("Escreva algo para continuar!")
                        else:
                            with st.spinner("Cliente pensando..."):
                                st.session_state.historico_chat.append({"role": "Vendedor", "text": resposta})
                                
                                texto_conversa = "\n".join([f"{m['role']}: {m['text']}" for m in st.session_state.historico_chat])
                                prompt_cliente = f"""
                                Atue como um cliente de farmácia. Sua queixa principal é relacionada à falta de: {st.session_state.produto_alvo} (NÃO FALE O NOME DO PRODUTO, apenas sinta a dor).
                                Histórico da conversa até agora:
                                {texto_conversa}
                                
                                Como o cliente responderia à última fala do Vendedor? Seja curto (1 ou 2 frases), natural e direto. Sem aspas.
                                """
                                try:
                                    modelo_uso = MODELO_NOME if MODELO_NOME else "models/gemini-pro"
                                    model = genai.GenerativeModel(modelo_uso)
                                    res_cliente = model.generate_content(prompt_cliente)
                                    
                                    st.session_state.historico_chat.append({"role": "Cliente", "text": res_cliente.text.strip()})
                                    st.session_state.turno += 1
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro na conexão com IA: {e}")
                else:
                    st.info("Limite de perguntas atingido. Finalize a venda.")

            with col2:
                btn_tipo = "primary" if st.session_state.turno == 3 else "secondary"
                if st.button("✅ FINALIZAR E AVALIAR", type=btn_tipo):
                    if not resposta:
                        st.warning("Escreva sua resposta final / indicação do produto!")
                    else:
                        with st.spinner("O Coach está analisando o atendimento completo..."):
                            st.session_state.historico_chat.append({"role": "Vendedor", "text": resposta})
                            
                            texto_conversa_final = "\n".join([f"{m['role']}: {m['text']}" for m in st.session_state.historico_chat])
                            
                            prompt_aval = f"""
                            Aja como um gerente técnico de farmácia e coach de vendas.
                            
                            CONVERSA COMPLETA DO ATENDIMENTO:
                            {texto_conversa_final}
                            
                            PRODUTO ALVO ESPERADO: {st.session_state.produto_alvo}
                            
                            AVALIAÇÃO GERAL (Seja rigoroso):
                            1. Sondagem: Fez boas perguntas investigativas antes de ofertar?
                            2. Conexão: Foi empático e atencioso?
                            3. Oferta: Indicou o produto correto ({st.session_state.produto_alvo}) focando no BENEFÍCIO (e não só na característica)?
                            
                            SAÍDA:
                            Nota: [0 a 10]
                            [Feedback prático e direto avaliando o conjunto da conversa]
                            """
                            try:
                                modelo_uso = MODELO_NOME if MODELO_NOME else "models/gemini-pro"
                                model = genai.GenerativeModel(modelo_uso)
                                res_aval = model.generate_content(prompt_aval)
                                
                                st.session_state.feedback = res_aval.text
                                match = re.search(r"(\d+[\.,]\d+|\d+)", res_aval.text)
                                st.session_state.nota = float(match.group(0).replace(',', '.')) if match else 0.0
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao avaliar: {e}")

        # 4. RESULTADO E FEEDBACK
        if st.session_state.feedback:
            st.markdown("---")
            cor = "green" if st.session_state.nota >= 7 else "red"
            st.markdown(f"<h1 style='text-align: center; color: {cor}'>{st.session_state.nota}/10</h1>", unsafe_allow_html=True)
            
            with st.container(border=True):
                st.info(st.session_state.feedback)
            
            col_save, col_discard = st.columns(2)
            with col_save:
                if st.button("💾 SALVAR TREINO", type="primary"):
                    conversa_str = " | ".join([f"{m['role']}: {m['text']}" for m in st.session_state.historico_chat])
                    salvar_sessao({
                        "Data": datetime.now().strftime("%d/%m %H:%M"), 
                        "Colaborador": colaborador, 
                        "ProdutoAlvo": st.session_state.produto_alvo,
                        "Conversa": conversa_str, 
                        "Nota": st.session_state.nota, 
                        "FeedbackIA": st.session_state.feedback
                    })
                    st.success("Salvo!")
                    st.session_state.historico_chat = []
                    st.session_state.feedback = ""
                    st.rerun()
            with col_discard:
                if st.button("🗑️ DESCARTAR"):
                    st.session_state.historico_chat = []
                    st.session_state.feedback = ""
                    st.rerun()
