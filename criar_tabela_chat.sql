CREATE TABLE IF NOT EXISTS chat_historico (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agente text DEFAULT 'ATLAS',
  mensagem text,
  resposta text,
  clinicas_encontradas int DEFAULT 0,
  criado_em timestamp DEFAULT now()
);

CREATE TABLE IF NOT EXISTS emails (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  clinica_id uuid REFERENCES clinicas(id),
  remetente text,
  destinatario text,
  assunto text,
  corpo text,
  data_envio timestamp DEFAULT now(),
  data_resposta timestamp,
  respondeu boolean DEFAULT false,
  status text DEFAULT 'nao_enviado'
);
