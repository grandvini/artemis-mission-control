# 🛰️ Artemis II: Real-Time Mission Control

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Data](https://img.shields.io/badge/Data-NASA_JPL_Horizons-black)
![License](https://img.shields.io/badge/License-MIT-green)

Um dashboard interativo e em tempo real construído em Python para monitorar a telemetria, mecânica orbital e a infraestrutura de comunicação na Terra durante a missão tripulada **Artemis II** da NASA.

---

## 📸 Preview do Dashboard

> **Nota:** Adicione aqui um print bem bonito do seu painel rodando!
> *(Arraste uma imagem do dashboard aberto no seu navegador para dentro do GitHub e ele vai gerar o link automaticamente aqui).*

---

## ✨ Principais Funcionalidades

* ⏱️ **Splashdown ETA:** Contagem regressiva de precisão (baseada em *timezone-aware UTC*) para a reentrada e pouso da cápsula Orion no Oceano Pacífico.
* 📡 **DSN Tracker:** Sistema de varredura no feed XML da *Deep Space Network* que identifica qual antena na Terra (Madrid, Goldstone ou Canberra) está trancada no sinal da nave e quais bandas de rádio (S/X) estão ativas.
* 📈 **Motor de Efemérides (JPL Horizons):** Consumo da API do JPL para calcular a distância geocêntrica, altitude lunar real e velocidade (Range Rate) através de cálculos vetoriais.
* 🚨 **Integração com Telegram:** Bot configurado via webhook para disparar alertas de zona de sombra (*Loss of Signal - LOS*) baseados na geometria orbital.
* 📺 **Visualização Tática:** Integração do simulador AROW 3D da NASA e feed de vídeo em tempo real renderizados lado a lado.

---

## 🚀 Como Executar o Projeto Localmente

É extremamente simples subir este Mission Control na sua própria máquina.

### Pré-requisitos
Certifique-se de ter o Python instalado. O projeto foi testado em versões 3.12+.

### 1. Clonar e Instalar
Abra o seu terminal, clone o repositório e instale as dependências:

```bash
git clone [https://github.com/SEU_USUARIO/artemis-mission-control.git](https://github.com/SEU_USUARIO/artemis-mission-control.git)
cd artemis-mission-control
pip install -r requirements.txt

### 2. Configurar o Telegram (Opcional)
Se desejar receber os alertas no seu celular, edite o arquivo `dashboard_artemis.py` e insira as suas credenciais nas variáveis `bot_token` e `chat_id`. 

### 3. Rodar a Aplicação
Se você estiver no Windows, basta dar dois cliques no arquivo:
👉 `run.bat`

Ou inicie manualmente via terminal:
```bash
streamlit run dashboard_artemis.py
