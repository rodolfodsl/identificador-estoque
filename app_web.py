import streamlit as st
import pandas as pd
from PIL import Image

# Configuração da página do app
st.set_page_config(
    page_title="Mocinha Biju - Identificador de Estoque",
    page_icon="💎",
    layout="centered"
)

# Estilo visual com a identidade da marca (Cores e fontes)
st.markdown("""
    <style>
    .main-title {
        color: #e12d74;
        font-weight: bold;
    }
    .stButton>button {
        background-color: #e12d74;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='main-title'>💎 Mocinha Biju - Consulta de Estoque</h2>", unsafe_allow_html=True)
st.write("Tire uma foto da etiqueta ou envie a imagem para identificar o produto unificando Bling e WhatsApp.")

# Botão ou área para carregar / tirar a foto direto pelo celular ou pc
arquivo_foto = st.file_uploader("Envie ou tire a foto da etiqueta/peça:", type=["jpg", "jpeg", "png"])

if arquivo_foto is not None:
    # Mostra a foto enviada na tela
    imagem = Image.open(arquivo_foto)
    st.image(imagem, caption="Foto enviada para análise", use_column_width=True)
    
    if st.button("🔍 Identificar Produto"):
        with st.spinner("Analisando imagem, cruzando com Bling e Planilha..."):
            
            # Simulando o reconhecimento e cruzamento dos dados
            codigo_detectado = "185918" # Exemplo de código lido
            descricao_bling = "FAIXA FRANZIDA PRETA"
            assertividade = 98.5
            preco = 19.90
            estoque = 14
            
            # Exibindo os resultados estruturados
            st.success("¡Análise concluída com sucesso!")
            
            st.markdown("### 📊 Resultado da Identificação")
            st.markdown(f"**• Código Detectado:** `{codigo_detectado}`")
            st.markdown(f"**• Produto (Bling ERP):** {descricao_bling}")
            st.markdown(f"**• Assertividade:** :green[**{assertividade}%**]")
            st.markdown(f"**• Preço de Venda:** R$ {preco:.2f}")
            st.markdown(f"**• Saldo em Estoque:** {estoque} unidades")
