WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY COALESCE(score,0) DESC) as rn
    FROM clinicas
)
UPDATE clinicas 
SET status = 'inativo'
WHERE id IN (SELECT id FROM ranked WHERE rn > 50);