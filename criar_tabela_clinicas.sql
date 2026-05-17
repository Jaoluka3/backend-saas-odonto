CREATE TABLE clinicas (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  nome text NOT NULL,
  telefone text UNIQUE,
  email text,
  website text,
  endereco text,
  cidade text,
  avaliacao_google float,
  num_avaliacoes int,
  score int DEFAULT 0,
  status text DEFAULT 'novo'
    CHECK (status IN ('novo','qualificado','descartado','contactado','inativo','cliente')),
  mensagem_enviada text,
  data_contato timestamp,
  numero_followups int DEFAULT 0,
  criado_em timestamp DEFAULT now()
);

-- Indices para queries frequentes
CREATE INDEX idx_clinicas_status ON clinicas (status);
CREATE INDEX idx_clinicas_score ON clinicas (score DESC);
