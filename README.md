# MotionCopy AI — backend pronto para Render

## 1. O que é
API Python/FastAPI para receber um vídeo, solicitar análise multimodal ao Gemini e devolver:
- resumo dos movimentos;
- cronologia com tempos aproximados;
- incertezas;
- prompts resumido, detalhado e universal.

O vídeo é tratado como referência de movimento, não de cenário/aparência.

## 2. Publicar no Render usando GitHub
1. Extraia este ZIP no celular ou computador.
2. No GitHub, crie um repositório privado chamado `motioncopy-ai`.
3. Envie para a raiz do repositório TODOS os itens extraídos, incluindo a pasta `app`, `requirements.txt`, `render.yaml`, `.gitignore` e README.
4. No Render, selecione New > Blueprint e conecte o repositório.
5. O Render vai ler `render.yaml`. Quando pedir `GEMINI_API_KEY`, cole a chave no campo secreto do Render, não no GitHub.
6. Confirme a criação. Aguarde o deploy terminar.

## 3. Testar
Abra `https://SEU-SERVICO.onrender.com/health`. Deve retornar:
`{"ok":true,"service":"MotionCopy AI API"}`

A documentação da API fica em `https://SEU-SERVICO.onrender.com/docs`.

## 4. Endpoint de análise
POST `/api/analyze`, `multipart/form-data`, campo `video`.

Exemplo de resposta:
- `summary`
- `timeline`
- `uncertainties`
- `prompts.short`
- `prompts.detailed`
- `prompts.universal`

## 5. Segurança
- Não envie a chave Gemini ao GitHub.
- Não cole a chave em chats, capturas de tela ou no frontend.
- Configure `GEMINI_API_KEY` apenas na área Environment/Secrets do Render.
- O serviço gratuito pode entrar em suspensão após inatividade e demorar para responder na primeira chamada.
- O plano gratuito, limites da API Gemini, disponibilidade do modelo e custos podem mudar. Verifique no painel do provedor antes de usar em escala.
- Antes de produção, adicione autenticação, limites de requisição, validação de tamanho/duração, proteção contra abuso, política de privacidade e monitoramento.
