import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
import plotly.express as px
import streamlit.components.v1 as components
import xml.etree.ElementTree as ET
from astroquery.jplhorizons import Horizons
from astropy.time import Time
from datetime import datetime, timedelta, timezone
import requests
from astroquery.jplhorizons import Horizons, conf
conf.timeout = 120  # Dá 2 minutos de paciência para o servidor da NASA

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Artemis II Mission Control", page_icon="🚀", layout="wide")

# --- CONTROLE DE ALERTAS ---
if "splashdown_alert_sent" not in st.session_state:
    st.session_state.splashdown_alert_sent = False

# URL do seu Webhook (opcional)
WEBHOOK_URL = "" 

def send_alert(message):
    bot_token = "SEU_BOT_TOKEN_AQUI"
    chat_id = "SEU_TOKEN_AQUI"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": message})
    except Exception as e:
        st.toast("Erro ao enviar Telegram", icon="⚠️")

# --- CAPTURA DA ANTENA ---
@st.cache_data(ttl=60)
def get_dsn_status():
    try:
        url = "https://eyes.nasa.gov/dsn/data/dsn.xml"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() 
        
        root = ET.fromstring(response.content)
        
        # Nossa lista atualizada com o "Cheat Code" que descobrimos
        alvos_orion = ['EM2', 'ORION', 'ARTEMIS']
        
        for dish in root.findall('.//dish'):
            targets = dish.findall('.//target')
            for target in targets:
                name = target.get('name', '').upper()
                
                # Se bater com EM2, ele formata e devolve pro painel
                if any(alvo in name for alvo in alvos_orion):
                    
                    # Vamos caçar as tags de sinal (Downlink e Uplink)
                    down_signal = dish.find('downSignal')
                    up_signal = dish.find('upSignal')
                    
                    # Pega a banda se a tag existir e não for vazia
                    b_down = down_signal.get('band') if down_signal is not None else ""
                    b_up = up_signal.get('band') if up_signal is not None else ""
                    
                    # Junta as bandas encontradas (ex: "S" ou "S/Ka")
                    bandas_ativas = [b for b in [b_down, b_up] if b != ""]
                    
                    if bandas_ativas:
                        # Remove duplicatas com set() e junta com barra
                        banda_final = "/".join(set(bandas_ativas))
                    else:
                        banda_final = "S/Ka (Tracking)"
                        
                    return {
                        'antena': dish.get('name'),
                        'banda': banda_final
                    }
        return None
    except:
        return None

# --- METEOROLOGIA OCEÂNICA (CACHE: 10 MIN) ---
@st.cache_data(ttl=600)
def get_splashdown_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=32.7157&longitude=-117.1611&current_weather=true"
        
        # O disfarce para a API não bloquear nosso script Python
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
        }
        
        # Aumentei a paciência (timeout) de 5 para 10 segundos
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() 
        
        data = response.json()
        return data['current_weather']
        
    except Exception as e:
        # Se der erro agora, o Streamlit vai gritar o motivo no canto da tela!
        st.toast(f"Erro na API de Clima: {e}", icon="⚠️")
        return None

# --- EXTRAÇÃO DE DADOS (CACHE: 5 MINUTOS) ---    
@st.cache_data(ttl=300)
def fetch_mission_data():
    # O jeito moderno e à prova de falhas de pegar o UTC agora:
    now = datetime.now(timezone.utc)
    
    # 🚨 MODO DE EMERGÊNCIA: Pede apenas 1 hora do passado e 4 horas do futuro
    # Isso reduz o payload em quase 70% e a NASA processa muito mais rápido!
    start_time = now - timedelta(hours=1)
    stop_time = now + timedelta(hours=4)
    
    epochs = {
        'start': start_time.strftime('%Y-%m-%d %H:%M'),
        'stop': stop_time.strftime('%Y-%m-%d %H:%M'),
        'step': '1m' # Mantemos a precisão de 1 minuto!
    }
    
    # Centro da Terra (500@399) e Centro da Lua (500@301)
    obj_earth = Horizons(id='-1024', location='500@399', epochs=epochs)
    vec_earth = obj_earth.vectors().to_pandas()
    
    obj_moon = Horizons(id='-1024', location='500@301', epochs=epochs)
    vec_moon = obj_moon.vectors().to_pandas()
    
    df = vec_earth[['datetime_jd', 'x', 'y', 'z', 'range', 'range_rate']].copy()
    df.columns = ['jd', 'x_e', 'y_e', 'z_e', 'dist_earth_au', 'vel_au_d']
    df['dist_moon_au'] = vec_moon['range']
    
    AU_TO_KM = 149597870.7
    df['dt'] = pd.to_datetime([Time(jd, format='jd').iso for jd in df['jd']])
    
    # --- CONVERSÃO PARA FUSO DE SP (UTC-3) ---
    df['dt'] = df['dt'] - pd.Timedelta(hours=3)
    
    df['dist_earth_km'] = df['dist_earth_au'] * AU_TO_KM
    
    # --- CALCULA A DISTÂNCIA ATÉ O CENTRO DA LUA ---
    df['dist_moon_km'] = df['dist_moon_au'] * AU_TO_KM
    
    # --- O HOTFIX DA ALTITUDE ---
    RAIO_LUNAR_KM = 1737.4
    df['dist_moon_km'] = df['dist_moon_km'] - RAIO_LUNAR_KM  # Transforma Centro em Superfície
    
    df['vel_kmh'] = (df['vel_au_d'].abs() * AU_TO_KM) / 24
    
    return df

# --- INTERFACE PRINCIPAL ---
st.title("🛰️ Artemis II: Real-Time Mission Control")

with st.spinner("Sincronizando com JPL Horizons..."):
    df = fetch_mission_data()
    
    # Relógio local de SP para sincronizar com o DataFrame
    now_sp = datetime.utcnow() - timedelta(hours=3)
    
    # Pega a linha mais próxima do horário de SP
    current_idx = (df['dt'] - now_sp).abs().idxmin()
    now_data = df.loc[current_idx]

# --- BLOCO 0: CRONÔMETRO DE SPLASHDOWN (ETA) ---
st.markdown("### ⏱️ Contagem Regressiva para o Pouso (Splashdown)")

# A data oficial do Splashdown confirmada pela NASA (21:07 SP = 00:07 UTC do dia 11)
TARGET_SPLASHDOWN = datetime(2026, 4, 11, 0, 7, 0, tzinfo=timezone.utc)

# Puxando o horário UTC exato de agora (usando a sintaxe moderna que acabamos de corrigir)
now_utc = datetime.now(timezone.utc)
time_remaining = TARGET_SPLASHDOWN - now_utc

# Lógica do Cronômetro e Alerta Telegram
if time_remaining.total_seconds() > 0:
    days = time_remaining.days
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Exibe o ETA com destaque visual
    st.info(f"**Tempo Restante de Voo:** {days} dias, {hours:02d} horas e {minutes:02d} minutos")
    
    # --- NOVO: GATILHO DO TELEGRAM (3 HORAS PARA O POUSO) ---
    # 3 horas = 10800 segundos. Verifica se já não enviou antes.
    if time_remaining.total_seconds() <= 10800:
        if not st.session_state.splashdown_alert_sent:
            mensagem_alerta = (
                "🚨 ALERTA TÁTICO: REENTRADA ARTEMIS II 🚨\n\n"
                "A cápsula Orion está a menos de 3 horas do Splashdown no Pacífico!\n\n"
                f"🔥 Velocidade de Queda: {now_data['vel_kmh']:,.0f} km/h\n"
                f"🌍 Distância da Atmosfera: {now_data['dist_earth_km']:,.0f} km\n\n"
                "Abra o Mission Control agora. O blackout de plasma vai começar em breve!"
            )
            send_alert(mensagem_alerta)
            st.session_state.splashdown_alert_sent = True # Trava para não enviar de novo
            
    # Barra de progresso visual da viagem de volta
    distancia_maxima_retorno = 413145.0
    distancia_atual = now_data['dist_earth_km']
    
    progresso_retorno = 1.0 - (distancia_atual / distancia_maxima_retorno)
    progresso_seguro = max(0.0, min(progresso_retorno, 1.0)) 
    
    st.progress(progresso_seguro, text="Progresso da Queda Livre rumo à Terra")

else:
    st.success("🌊 SPLASHDOWN! A tripulação da Artemis II retornou em segurança à Terra!")
    st.balloons()  

# --- CÁLCULOS ORBITAIS AVANÇADOS ---
RAIO_TERRA_KM = 6371.0
# Subtrai o núcleo da Terra para sabermos a altitude real da nave
altitude_superficie = max(0.0, now_data['dist_earth_km'] - RAIO_TERRA_KM)

# 1 Mach = 1234.8 km/h (ao nível do mar)
mach_atual = now_data['vel_kmh'] / 1234.8

# Cálculo da Força G (Desaceleração Bruta)
try:
    # Pegamos a velocidade de 1 minuto atrás para ver o quão violenta é a frenagem
    v_prev_kmh = df.loc[current_idx - 1, 'vel_kmh']
    delta_v_ms = (now_data['vel_kmh'] - v_prev_kmh) / 3.6
    
    # Nosso intervalo (step) na API é de 60 segundos
    aceleracao_ms2 = delta_v_ms / 60.0
    
    # 1G = 9.80665 m/s². Usamos abs() porque é a força de esmagamento sentida
    forca_g = abs(aceleracao_ms2 / 9.80665) 
    
    # Somamos 1.0G (gravidade normal) para o voo de cruzeiro
    forca_g_display = max(1.0, forca_g)
except:
    forca_g_display = 1.0 # Falback de segurança

# --- BLOCO 1: KPIs DE RETORNO (INBOUND) ---
st.subheader("🎯 Telemetria de Retorno (Inbound)")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    # A Métrica com o Mach Meter embutido!
    st.metric(label="Velocidade de Retorno", 
              value=f"{now_data['vel_kmh']:,.0f} km/h".replace(',', '.'),
              delta=f"Mach {mach_atual:.1f}", delta_color="off")

with col2:
    # Mostrando a Altitude Real como destaque e a Distância Geocêntrica (Núcleo) em letras mais pequenas
    dist_nucleo = f"{now_data['dist_earth_km']:,.0f} km".replace(',', '.')
    st.metric(label="Altitude Real (Superfície)", 
              value=f"{altitude_superficie:,.0f} km".replace(',', '.'),
              delta=f"Dist. Núcleo: {dist_nucleo}", delta_color="off")

with col3:
    # Sai a Lua, entra o G-Meter!
    alerta_g = "Gravidade Normal" if forca_g_display < 1.5 else "ALTA COMPRESSÃO ⚠️"
    cor_g = "off" if forca_g_display < 1.5 else "inverse"
    
    st.metric(label="Força G (Desaceleração)", 
              value=f"{forca_g_display:.2f} G", 
              delta=alerta_g, delta_color=cor_g)

with col4:
    clima = get_splashdown_weather()
    if clima:
        vento = clima['windspeed']
        # Se o vento passar de 30 km/h, os helicópteros de resgate têm problemas
        status_mar = "SEGURO 🟢" if vento < 30.0 else "ALERTA MARINHA 🟡"
        st.metric(label="Clima no Pacífico", value=f"{clima['temperature']}°C", delta=f"Vento: {vento} km/h | {status_mar}", delta_color="off")
    else:
        st.metric(label="Clima no Pacífico", value="Buscando...", delta="Aguardando satélite")

with col5:
    dsn_data = get_dsn_status()
    if dsn_data:
        st.metric(label="Antena DSN", value=dsn_data['antena'], delta=f"Banda: {dsn_data['banda']}")
    else:
        st.metric(label="Antena DSN", value="Buscando...", delta="Aguardando Link")

# --- INFO EXTRA: GLOSSÁRIO DSN ---
with st.expander("ℹ️ O que significa a Antena e a Banda?"):
    st.info("""
    **📡 O que é a Antena (Ex: DSS-26)?**
    Significa *Deep Space Station*. A NASA possui 3 complexos no mundo (Goldstone-EUA, Madrid-Espanha e Canberra-Austrália) para que a nave nunca saia do campo de visão enquanto a Terra gira. A **DSS-26**, por exemplo, é uma antena parabólica gigante de 34 metros de diâmetro localizada no Deserto de Mojave, na Califórnia.

    **📻 O que são as Bandas de Rádio?**
    * **Banda S (S-Band):** É o "telefone fixo" da nave. Uma frequência mais baixa (2-4 GHz), porém extremamente confiável e resistente a interferências. É por aqui que trafega a **telemetria crítica**: batimentos cardíacos dos astronautas, nível de oxigênio e comandos vitais de navegação.
    * **Banda X (X-Band):** É a via de "dados rápidos" (8-12 GHz). Permite enviar pacotes de dados maiores, fazer o rastreamento exato da órbita e transmitir áudio/vídeo comprimido.
    * **Banda Ka:** A banda super larga de rádio, acionada para altíssimos volumes de dados.
    
    *Nota: O vídeo em alta resolução (4K) da missão utiliza o sistema O2O (Laser Óptico), que opera independente das antenas de rádio da DSN.*
    """)     

# --- ALERTA TÁTICO: PLASMA BLACKOUT ---
# A 122 km de altitude a atmosfera fica densa e a nave pega fogo.
if altitude_superficie <= 122.0 and altitude_superficie > 5.0:
    st.error("""
    🔥 **⚠️ ENTRY INTERFACE ATINGIDA (122 km): INÍCIO DO PLASMA BLACKOUT!** A fricção atmosférica gerou um escudo de plasma a 2.700 °C ao redor da cápsula Orion. 
    **PERDA TOTAL DE TELEMETRIA E RÁDIO CONFIRMADA.** A antena DSN está cega. 
    Aguardando abertura dos paraquedas...
    """, icon="🚨")

st.divider()

# --- BLOCO 1.1: VELOCÍMETRO ANALÓGICO ---
# Criamos 3 colunas e usamos a do meio para o gráfico não ficar muito largo
col_vazia1, col_gauge, col_vazia2 = st.columns([1, 2, 1])

with col_gauge:
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = now_data['vel_kmh'],
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Velocidade Orbital Atual", 'font': {'size': 24, 'color': 'white'}},
        number = {'suffix': " km/h", 'font': {'size': 40, 'color': '#00FFFF'}}, # Azul ciano
        gauge = {
            'axis': {'range': [None, 40000], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': "#00FFFF"}, # A barra que preenche
            'bgcolor': "black",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 15000], 'color': "#1a1a1a"}, # Cinza escuro (cruzeiro)
                {'range': [15000, 30000], 'color': "#333333"}, # Cinza médio (acelerando)
                {'range': [30000, 40000], 'color': "#4d4d4d"}  # Cinza claro (estilingue máximo)
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 39500 # Marca de velocidade crítica
            }
        }
    ))
    
    fig_gauge.update_layout(
        height=350, 
        template="plotly_dark", 
        margin=dict(l=20, r=20, b=20, t=50),
        paper_bgcolor="rgba(0,0,0,0)", # Fundo transparente
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()

# --- BLOCO 1.2: OPERAÇÕES DE RESGATE (SPLASHDOWN) ---
st.subheader("🪂 Operações de Resgate e Pouso (Zona de Exclusão)")

col_para, col_mapa = st.columns([1, 2])

with col_para:
    st.markdown("**Sequenciador Autônomo de Paraquedas**")
    st.markdown("<span style='font-size: 0.9em; color: gray;'>O computador de bordo (Flight Controller) aciona os sistemas de frenagem baseado exclusivamente na queda de altitude.</span>", unsafe_allow_html=True)
    
    # Função auxiliar para marcar o check verde dinamicamente
    def check(target):
        return "✅" if altitude_superficie <= target else "⏳"
        
    st.info(f"""
    **Altitude Atual:** {altitude_superficie:,.1f} km
    
    * {check(122.0)} **122.0 km** - Entry Interface (Plasma Blackout)
    * {check(7.3)} **7.3 km** - Ejeção da Capa Protetora
    * {check(7.0)} **7.0 km** - Paraquedas de Frenagem (Drogue)
    * {check(2.5)} **2.5 km** - Paraquedas Principais (Main)
    * {check(0.0)} **0.0 km** - Impacto na Água (Splashdown)
    """)
    
with col_mapa:
    st.markdown("**Mapa Tático: Costa de San Diego (USS San Diego)**")
    # Ponto de resgate estimado da Marinha: Alto mar, oeste da Califórnia
    df_mapa = pd.DataFrame({
        'lat': [32.6000],
        'lon': [-117.6000]
    })
    # O Streamlit renderiza um mapa de satélite interativo com zoom automático
    st.map(df_mapa, zoom=7, use_container_width=True)

st.divider()

# --- BLOCO 2: VÍDEOS AO VIVO ---
st.subheader("📺 Multi-Feed de Comunicação (Vídeo)")

# O truque das colunas: [1, 1.5, 1] cria margens nas pontas e um espaço central
col_esq, col_meio, col_dir = st.columns([1, 1.5, 1])

with col_meio:
    # Centralizando o título com HTML simples
    st.markdown("<div style='text-align: center;'><b>Cobertura Oficial (Mission Control)</b></div>", unsafe_allow_html=True)
    
    # Colocamos o width em "450" e height em "350" (bem mais quadradinho)
    # E o <div style="display: flex; justify-content: center;"> garante que fique cravado no meio
    components.html("""
    <div style="display: flex; justify-content: center;">
        <iframe width="450" height="350" src="https://www.youtube.com/embed/m3kR2KK8TEs?autoplay=1&mute=1" title="Official Broadcast" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
    </div>
    """, height=360)

st.divider()

# --- BLOCO 3: GRÁFICOS E MODELOS 3D ---
st.subheader("📍 Trajetória e Visualização Espacial")

# Criamos três abas separadas
aba1, aba2, aba3 = st.tabs(["📈 Nossos Gráficos (Leve)", "🚀 Simulador AROW da NASA (Pesado)", "ℹ️ Entenda a Trajetória"])

with aba1:
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.markdown("**Trajetória 3D (Referencial Geocêntrico)**")
        fig_3d = go.Figure()
        fig_3d.add_trace(go.Scatter3d(
            x=df['x_e'], y=df['y_e'], z=df['z_e'],
            mode='lines', line=dict(color='cyan', width=4), name='Órbita'
        ))
        fig_3d.add_trace(go.Scatter3d(
            x=[now_data['x_e']], y=[now_data['y_e']], z=[now_data['z_e']],
            mode='markers', marker=dict(size=8, color='red'), name='Orion Agora'
        ))
        fig_3d.add_trace(go.Scatter3d(
            x=[0], y=[0], z=[0], mode='markers', marker=dict(size=12, color='blue'), name='Terra'
        ))
        fig_3d.update_layout(template="plotly_dark", margin=dict(l=0, r=0, b=0, t=0), height=400)
        st.plotly_chart(fig_3d, use_container_width=True)

    with col_graf2:
        st.markdown("**Efeito Estilingue: Velocidade**")
        fig_vel = px.area(df, x='dt', y='vel_kmh', labels={'vel_kmh': 'Velocidade (km/h)', 'dt': 'Data/Hora (SP)'})
        fig_vel.add_vline(x=now_data['dt'], line_dash="dash", line_color="yellow")
        fig_vel.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, b=0, t=0))
        st.plotly_chart(fig_vel, use_container_width=True)

with aba2:
    st.info("💡 **Dica de Performance:** O modelo 3D abaixo exige bastante do navegador. Se a tela engasgar, volte para a aba 'Nossos Gráficos'.")
    # Embutindo o site oficial do AROW
    components.iframe("https://www.nasa.gov/missions/artemis-ii/arow/", height=600, scrolling=True)

with aba3:
    st.write("Nesta missão, a Orion não vai entrar na órbita da Lua. Ela fará um 'Flyby de Retorno Livre', usando a gravidade lunar como um estilingue para ser arremessada de volta para a Terra sem gastar combustível.")

# --- SIDEBAR: EXPORTAÇÃO E AUTO-REFRESH ---
st.sidebar.title("⚙️ Controles")
st.sidebar.markdown("Gerencie o painel de BI.")

# Download CSV
csv = df.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("⬇️ Baixar Telemetria (CSV)", data=csv, file_name='artemis_telemetria.csv', mime='text/csv')

st.sidebar.divider()

# Auto-Refresh
st.sidebar.subheader("🔄 Auto-Refresh")
auto_refresh = st.sidebar.checkbox("Atualizar a cada 60s", value=True)

if st.sidebar.button("Teste Telegram"):
    send_alert("Houston, temos um teste de comunicação com sucesso!")

st.sidebar.divider()
st.sidebar.subheader("📋 Resumo da Operação")
st.sidebar.info("""
**Missão:** Artemis II
**Tripulação:** Wiseman, Glover, Koch, Hansen
**Fase Atual:** Retorno à Terra (Inbound)
**Alvo de Pouso:** Oceano Pacífico (Costa de San Diego)
""")

# --- BARRA DE PROGRESSO DO RETORNO (SIDEBAR) ---
st.sidebar.markdown("**Progresso de Retorno a Terra:**")

# Calculando o progresso da queda livre (de 413.145 km até 0)
distancia_atual_terra = now_data['dist_earth_km']
distancia_recorde = 413145.0 # O recorde batido no lado oculto da Lua

progresso_retorno_sidebar = 1.0 - (distancia_atual_terra / distancia_recorde)

# O Streamlit exige que o valor do progress fique exatamente entre 0.0 e 1.0
st.sidebar.progress(max(0.0, min(progresso_retorno_sidebar, 1.0)))

if auto_refresh:
    st.sidebar.caption("⏳ Atualizando em background...")
    time.sleep(60)
    st.rerun()
