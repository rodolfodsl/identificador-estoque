import streamlit as st
import pandas as pd
import requests
import base64
from io import BytesIO
from PIL import Image
import json
from google import genai

st.set_page_config(page_title="Identificador Visual Automatizado", layout="centered")
st.title("🧠 Identificador Visual & Consulta por Código")

# --- CREDENCIAIS FIXAS ---
CLIENT_ID = "416443567d77b7d8eb18a6f15e6e207f21d1d534"
CLIENT_SECRET = "408062f863be604e4f3a5c2edd2638962d97d32b8ffea1054b9dc9b24a25"

# CHAVE DO GOOGLE FIXA (NUNCA MAIS PEDE)
CHAVE_GOOGLE_FIXA = "aq09d6cbd96cc41f25b3f3b30a5c13855"

# --- BARRA LATERAL PARA O CÓDIGO DO BLING ---
st.sidebar.header("🔑 Conexão Bling")
st.sidebar.info("Cole um novo código de autorização do Bling caso o token expire:")
auth_code_input = st.sidebar.text_input("Código de Autorização do Bling:", type="password")

if st.sidebar.button("🔗 Conectar Bling"):
    if auth_code_input:
        try:
            token_url = "https://api.bling.com.br/Api/v3/oauth/token"
            credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0"}
            data = {"grant_type": "authorization_code", "code": auth_code_input.strip()}
            
            resp_token = requests.post(token_url, headers=headers, data=data)
            token_data = resp_token.json()
            
            if "access_token" in token_data:
                st.session_state['bling_token'] = token_data["access_token"]
                st.sidebar.success("Bling conectado com sucesso!")
                st.rerun()
            else:
                st.sidebar.error(f"Erro: {token_data.get('description', 'Código inválido ou expirado.')}")
        except Exception as e:
            st.sidebar.error(f"Erro de conexão: {e}")
    else:
        st.sidebar.warning("Digite o código.")

def baixar_foto_bling_unica(id_produto, token):
    headers_api = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = requests.get(f"https://api.bling.com.br/Api/v3/produtos/{id_produto}", headers=headers_api, timeout=5)
        if resp.status_code == 200:
            imagens = resp.json().get('data', {}).get('midia', {}).get('imagens', {})
            link_foto = None
            if isinstance(imagens, dict):
                ext = imagens.get('externas', [])
                int_img = imagens.get('internas', [])
                if ext: link_foto = ext[0].get('link')
                elif int_img: link_foto = int_img[0].get('linkMiniatura') or int_img[0].get('link')
            elif isinstance(imagens, list) and len(imagens) > 0:
                link_foto = imagens[0].get('link') or imagens[0].get('url')
                
            if link_foto:
                headers = {'User-Agent': 'Mozilla/5.0'}
                if 'bling.com.br' in link_foto: headers['Authorization'] = f'Bearer {token}'
                url_limpa = str(link_foto).split(',')[0].split('|')[0].strip()
                if url_limpa.startswith("//"): url_limpa = "https:" + url_limpa
                resp_img = requests.get(url_limpa, headers=headers, timeout=5)
                if resp_img.status_code == 200:
                    return Image.open(BytesIO(resp_img.content)).convert('RGB')
    except Exception:
        pass
    return None

if 'bling_token' in st.session_state:
    st.success("✅ Bling Conectado e Pronto!")
    st.divider()
    
    arquivo_csv = st.file_uploader("Arraste o arquivo .csv do Bling", type=['csv'])
    
    if arquivo_csv:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        if 'ID' in df.columns and 'Descrição' in df.columns:
            
            aba_escolha = st.radio("Como você quer consultar o item?", ["📷 Identificação Visual por Câmera", "🏷️ Buscar por Código de Barras / SKU"])
            st.divider()
            
            if aba_escolha == "🏷️ Buscar por Código de Barras / SKU":
                st.info("Digite ou escaneie o código de barras/SKU impresso na etiqueta.")
                codigo_digitado = st.text_input("Código de Barras / SKU:")
                
                if codigo_digitado:
                    col_codigo = 'Código' if 'Código' in df.columns else df.columns[0]
                    item_encontrado = df[df[col_codigo].str.contains(codigo_digitado.strip(), case=False, na=False)]
                    
                    if not item_encontrado.empty:
                        st.success("Item encontrado no catálogo!")
                        for _, row in item_encontrado.iterrows():
                            st.markdown(f"### Produto: {row['Descrição']}")
                            st.write(f"**ID:** `{row['ID']}` | **SKU / Código:** `{row.get('Código', 'N/A')}`")
                            
                            img_oficial = baixar_foto_bling_unica(str(row['ID']), st.session_state['bling_token'])
                            if img_oficial:
                                st.image(img_oficial, width=200)
                            else:
                                st.warning("Sem foto cadastrada no Bling para este item.")
                            st.divider()
                    else:
                        st.warning("Nenhum produto encontrado com este código de barras no CSV carregado.")

            else:
                termo = st.text_input("Qual categoria vamos buscar? (Ex: RELÓGIO):")
                
                if termo:
                    df_filtrado = df[df['Descrição'].str.contains(termo.upper(), na=False)].copy()
                    st.write(f"Encontrados **{len(df_filtrado)}** itens no catálogo.")
                    
                    lista_produtos = []
                    for _, row in df_filtrado.iterrows():
                        lista_produtos.append({"id": str(row['ID']), "nome": str(row['Descrição']), "sku": str(row.get('Código', ''))})
                    
                    if len(lista_produtos) > 0:
                        st.divider()
                        st.info("📸 **A câmera está liberada!** Tire a foto do produto para receber a porcentagem de precisão.")
                        
                        foto_tirada = st.camera_input("Fotografe a peça:")
                        
                        if foto_tirada:
                            img_original = Image.open(foto_tirada).convert('RGB')
                            
                            with st.spinner("📊 Analisando imagem e calculando compatibilidade..."):
                                try:
                                    client = genai.Client(api_key=CHAVE_GOOGLE_FIXA)
                                    
                                    buffered = BytesIO()
                                    img_original.save(buffered, format="JPEG")
                                    image_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                                    
                                    prompt = f"""
                                    Você é o especialista sênior de estoque da loja Mocinha Biju.
                                    Analise a foto enviada e compare com a lista de produtos abaixo.
                                    
                                    Lista JSON dos produtos cadastrados:
                                    {json.dumps(lista_produtos, ensure_ascii=False)}
                                    
                                    TAREFA:
                                    1. Encontre as 3 melhores opções de produtos correspondentes na lista.
                                    2. Atribua uma porcentagem estimada de precisão/compatibilidade (ex: 95, 80, 60) baseada nos detalhes visuais (cores, texturas, mostrador, pulseira).
                                    3. Retorne EXATAMENTE UM ARRAY JSON contendo 3 dicionários com as chaves 'id' e 'precisao'.
                                    Exemplo exato do formato esperado:
                                    [
                                        {{"id": "16629916212", "precisao": "98%"}},
                                        {{"id": "16629916213", "precisao": "82%"}},
                                        {{"id": "16629916214", "precisao": "65%"}}
                                    ]
                                    Retorne APENAS o JSON puro, sem crases, sem formatação markdown e sem texto adicional.
                                    """
                                    
                                    interaction = client.interactions.create(
                                        model="gemini-3.6-flash",
                                        input=[
                                            {
                                                "type": "image",
                                                "mime_type": "image/jpeg",
                                                "data": image_b64,
                                            },
                                            {"type": "text", "text": prompt},
                                        ],
                                    )
                                    
                                    texto_puro = interaction.output_text.replace('```json', '').replace('```', '').strip()
                                    itens_recomendados = json.loads(texto_puro)
                                    
                                    st.subheader("🎯 Resultados com Taxa de Precisão:")
                                    
                                    for rank, item_rec in enumerate(itens_recomendados):
                                        id_rec = item_rec.get("id")
                                        precisao = item_rec.get("precisao", "N/A")
                                        
                                        produto = next((item for item in lista_produtos if item["id"] == id_rec), None)
                                        if produto:
                                            st.markdown(f"### {rank+1}º Lugar: {produto['nome']} — **Compatibilidade: {precisao}**")
                                            col_1, col_2 = st.columns([1, 2])
                                            with col_1:
                                                img_oficial = baixar_foto_bling_unica(produto['id'], st.session_state['bling_token'])
                                                if img_oficial:
                                                    st.image(img_oficial, width=150)
                                                else:
                                                    st.warning("Sem foto no Bling")
                                            with col_2:
                                                st.write(f"**SKU:** `{produto['sku']}`")
                                            st.divider()
                                                
                                except Exception as e:
                                    st.error(f"Erro na análise de precisão: {e}")
else:
    st.warning("👈 Gere um novo código de autorização no painel do Bling e cole na barra lateral esquerda para conectar.")
