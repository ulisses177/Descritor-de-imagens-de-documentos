import os
import fitz  # PyMuPDF
import tiktoken
import re
import base64
import csv
from dotenv import load_dotenv
from openai import AzureOpenAI
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Carregar variáveis de ambiente
load_dotenv()

# Configurar cliente Azure OpenAI
client = AzureOpenAI(
    azure_endpoint=os.getenv("AOAI_ENDPOINT"),
    api_key=os.getenv("AOAI_API_KEY"),
    api_version="2024-02-15-preview"
)

deployment_name = os.getenv("AOAI_DEPLOYMENT")

# Definir o prompt template para geração de tutorial
tutorial_prompt_template = """
Você é um especialista em sistemas de gestão que cria tutoriais detalhados. Vou fornecer um contexto acumulado de uma funcionalidade em um sistema de gerenciamento e, com base nisso, gostaria que você escrevesse ou atualizasse um tutorial exaustivo passo a passo, semelhante ao exemplo que descreve a aprovação de inconsistências no sistema Exati. O tutorial deve seguir a mesma estrutura, com os seguintes pontos:

    1. Fluxo de navegação no sistema
    2. Passos detalhados sobre a configuração da nova funcionalidade
    3. Exemplos de interações visuais ou botões a serem clicados
    4. Opções de notificação ou personalização
    5. Definição de prioridades e confirmação final
    6. Outras funcionalidades ou opções relacionadas

Aqui está o contexto acumulado sobre o que o tutorial deve abordar:
{contexto_acumulado}

Por favor, atualize ou crie o tutorial de forma clara e coesa, seguindo a mesma abordagem direta usada no exemplo do sistema GUIA da Exati. Desconsidere os urls presentes no documento.
"""

# Definir o prompt template para geração de descrições de imagens
image_description_prompt_template = """
Você é um assistente de IA que descreve imagens em detalhes, considerando o contexto acumulado do tutorial. A imagem contém texto em português. Use o contexto fornecido para gerar uma descrição precisa e relevante.

Contexto Acumulado:
{contexto_acumulado}

Descrição da Imagem:
"""

# Função para remover URLs e informações redundantes
def clean_text(text):
    # Remove URLs
    text = re.sub(r'http\S+', '', text)
    # Remove espaços em branco excessivos
    text = re.sub(r'\s+', ' ', text)
    return text

# Função para contar tokens usando tiktoken
def count_tokens(text, encoding='gpt-4'):
    enc = tiktoken.encoding_for_model(encoding)
    return len(enc.encode(text))

# Função para dividir texto em chunks de aproximadamente 2000 tokens
def split_text_into_chunks(text, max_tokens=2000, encoding='gpt-4'):
    enc = tiktoken.encoding_for_model(encoding)
    tokens = enc.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk = enc.decode(tokens[i:i + max_tokens])
        chunks.append(chunk)
    return chunks

# Função para gerar ou atualizar o tutorial a partir do contexto acumulado usando Azure OpenAI
def generate_or_update_tutorial(contexto_acumulado):
    prompt = tutorial_prompt_template.format(contexto_acumulado=contexto_acumulado)
    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "Você é um assistente que ajuda a criar tutoriais detalhados."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Erro ao chamar a API OpenAI para tutorial: {e}")
        return ""

# Função para extrair texto do PDF
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        full_text += text + "\n"
    doc.close()
    cleaned_text = clean_text(full_text)
    return cleaned_text

# Função para extrair imagens do PDF e salvá-las em uma pasta
def extract_images_from_pdf(pdf_path, images_folder, contexto_acumulado):
    """
    Extri imagens e suas posições do PDF
    Retorna uma lista ordenada de dicionários com informações das imagens
    """
    if not os.path.exists(images_folder):
        os.makedirs(images_folder)
    
    doc = fitz.open(pdf_path)
    temp_image_info = []  # Lista temporária com todas as informações
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Primeiro, mapear imagens da página
        page_images = []
        for img in page.get_images(full=True):
            xref = img[0]
            base_image = doc.extract_image(xref)
            
            if base_image:
                page_images.append({
                    "xref": xref,
                    "image": base_image["image"],
                    "ext": base_image["ext"]
                })
        
        # Processar cada imagem e obter sua posição
        for img_index, image_data in enumerate(page_images):
            try:
                image_name = f"image_{page_num + 1}_{img_index + 1}.{image_data['ext']}"
                image_path = os.path.join(images_folder, image_name)
                
                # Salvar a imagem
                with open(image_path, "wb") as img_file:
                    img_file.write(image_data["image"])
                
                # Obter posição da imagem
                rect = None
                for item in page.get_image_info():
                    if "xref" in item and item["xref"] == image_data["xref"]:
                        rect = fitz.Rect(item["bbox"])
                        break
                
                # Gerar descrição
                description = get_image_description(image_path, contexto_acumulado)
                
                # Armazenar todas as informações para ordenação
                temp_image_info.append({
                    "image_name": image_name,
                    "description": description,
                    "_page": page_num,
                    "_rect": rect,
                    "_path": image_path,
                    "_y_pos": rect.y0 if rect else 0
                })
                
                logging.info(f"Imagem {image_name} processada com sucesso na página {page_num + 1}")
                
            except Exception as e:
                logging.error(f"Erro ao processar imagem na página {page_num + 1}: {e}")
                continue

    doc.close()
    
    # Ordenar por página e posição vertical
    temp_image_info.sort(key=lambda x: (x["_page"], x["_y_pos"]))
    
    # Criar lista final apenas com as informações necessárias
    final_image_info = [
        {
            "image_name": img["image_name"],
            "description": img["description"]
        }
        for img in temp_image_info
    ]
    
    return final_image_info

# Função para gerar descrição de uma imagem usando Azure OpenAI com contexto acumulado
def get_image_description(image_path, contexto_acumulado):
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"Erro ao ler a imagem {image_path}: {e}")
        return "Descrição não disponível devido a erro na leitura da imagem."

    prompt = image_description_prompt_template.format(
        contexto_acumulado=contexto_acumulado
    ) + f"![Imagem]({image_path})"

    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "Você é um assistente que descreve imagens com base em um contexto acumulado."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Erro ao chamar a API para a imagem {image_path}: {e}")
        return "Descrição não disponível devido a erro na chamada da API."

def create_output_markdown(cleaned_text, image_descriptions, tutorial_text, output_md_path):
    """
    Cria um arquivo markdown com texto limpo, imagens e tutorial
    """
    try:
        with open(output_md_path, "w", encoding="utf-8") as md_file:
            # Título principal
            md_file.write("# Documento Processado\n\n")
            
            # Seção 1: Texto Original com Imagens
            md_file.write("## Conteúdo Original\n\n")
            
            # Dividir o texto em parágrafos e inserir imagens nas posições relativas
            paragraphs = [p.strip() for p in cleaned_text.split('\n\n') if p.strip()]
            
            for paragraph in paragraphs:
                md_file.write(f"{paragraph}\n\n")
            
            # Seção 2: Imagens e Suas Descrições
            md_file.write("## Imagens do Documento\n\n")
            
            for img_desc in image_descriptions:
                # Caminho relativo para a imagem
                img_path = os.path.join("imagens_extraidas", img_desc["image_name"])
                if os.path.exists(img_path):
                    # Adicionar imagem
                    md_file.write(f"![{img_desc['image_name']}]({img_path})\n\n")
                    
                    # Adicionar descrição
                    md_file.write("**Descrição da Imagem:**\n")
                    md_file.write(f"{img_desc['description']}\n\n")
                    
                    # Adicionar separador
                    md_file.write("---\n\n")
            
            # Seção 3: Tutorial Gerado
            md_file.write("## Tutorial Gerado\n\n")
            md_file.write(f"{tutorial_text}\n\n")
            
        logging.info(f"Arquivo Markdown gerado com sucesso: {output_md_path}")
        
    except Exception as e:
        logging.error(f"Erro ao gerar arquivo Markdown: {e}")

def main(pdf_path, tutorial_output_path, images_folder, dataset_path, output_md_path):
    if not os.path.isfile(pdf_path):
        logging.error(f"O arquivo PDF '{pdf_path}' não existe.")
        return
    
    # Criar diretórios necessários
    os.makedirs(os.path.dirname(output_md_path), exist_ok=True)
    os.makedirs(images_folder, exist_ok=True)
    
    logging.info("Extraindo texto do PDF...")
    cleaned_text = extract_text_from_pdf(pdf_path)
    
    logging.info("Dividindo texto em chunks...")
    chunks = split_text_into_chunks(cleaned_text)
    logging.info(f"Total de chunks: {len(chunks)}")
    
    # Processar chunks e gerar tutorial
    contexto_acumulado = ""
    tutorial_text = ""
    
    for idx, chunk in enumerate(chunks):
        logging.info(f"Processando chunk {idx + 1}/{len(chunks)}...")
        contexto_acumulado += "\n" + chunk
        tutorial = generate_or_update_tutorial(contexto_acumulado)
        if tutorial:
            tutorial_text = tutorial
    
    # Extrair imagens e gerar descrições
    logging.info("Extraindo imagens e gerando descrições...")
    image_descriptions = extract_images_from_pdf(pdf_path, images_folder, contexto_acumulado)
    
    # Salvar descrições em CSV
    with open(dataset_path, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["image_name", "description"])
        writer.writeheader()
        for item in image_descriptions:
            writer.writerow(item)
    
    # Criar arquivo Markdown final
    logging.info("Gerando arquivo Markdown final...")
    create_output_markdown(cleaned_text, image_descriptions, tutorial_text, output_md_path)

if __name__ == "__main__":
    pdf_path = "documento.pdf"
    tutorial_output_path = "output/tutorial.md"
    images_folder = "imagens_extraidas"
    dataset_path = "output/descricao_imagens.csv"
    output_md_path = "output/documento_final.md"
    
    main(pdf_path, tutorial_output_path, images_folder, dataset_path, output_md_path)
a
