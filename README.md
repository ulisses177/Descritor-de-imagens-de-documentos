# PDF Tutorial Generator

Este projeto é um script em Python que extrai texto e imagens de arquivos PDF e gera tutoriais detalhados com base no conteúdo extraído. O resultado é um arquivo Markdown que inclui o texto limpo, as imagens extraídas e o tutorial gerado.

## Funcionalidades

- **Extração de Texto**: Remove URLs e espaços em branco excessivos do texto extraído do PDF.
- **Extração de Imagens**: Salva imagens extraídas em uma pasta especificada e gera descrições usando a API do Azure OpenAI.
- **Geração de Tutoriais**: Cria ou atualiza tutoriais detalhados com base em um contexto acumulado.
- **Criação de Arquivo Markdown**: Gera um arquivo Markdown que inclui o texto, as imagens e o tutorial.

## Pré-requisitos

Antes de executar o projeto, você precisará ter o Python 3.x instalado e as seguintes bibliotecas:

- `fitz` (PyMuPDF)
- `tiktoken`
- `python-dotenv`
- `openai`
- `logging`


