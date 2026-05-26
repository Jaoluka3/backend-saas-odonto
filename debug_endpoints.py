import os
import logging
from supabase_client import supabase
from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Create a router for debug endpoints
debug_router = APIRouter(prefix="/debug", tags=["debug"])

@debug_router.get("/score-distribution")
def get_score_distribution():
    """Returns distribution of clinics by score and status."""
    if not supabase:
        return {"success": False, "error": "Supabase not configured"}
    
    try:
        result = supabase.table("clinicas").select("id,nome,score,status,email,website").execute()
        clinicas = result.data or []
        
        if not clinicas:
            return {"success": True, "data": {"total": 0, "by_status": {}, "score_stats": {}}}
            
        total = len(clinicas)
        
        # Distribution by status
        status_count = {}
        for c in clinicas:
            s = c.get('status', 'unknown')
            status_count[s] = status_count.get(s, 0) + 1
        
        # Score statistics
        clinicas_com_score = [c for c in clinicas if c.get('score') is not None]
        score_stats = {}
        if clinicas_com_score:
            scores = [c.get('score') for c in clinicas_com_score]
            score_stats = {
                "count": len(clinicas_com_score),
                "min": min(scores),
                "max": max(scores),
                "mean": round(sum(scores) / len(scores), 1),
                "median": round(sorted(scores)[len(scores)//2]) if scores else 0
            }
            
            # Top 10 by score
            top_10 = sorted(clinicas_com_score, key=lambda c: c.get('score') or 0, reverse=True)[:10]
            score_stats["top_10"] = [
                {"nome": c['nome'], "score": c.get('score'), "status": c.get('status')}
                for c in top_10
            ]
        
        # Clinicas sem score
        score_stats["sem_score"] = len([c for c in clinicas if c.get('score') is None])
        
        return {
            "success": True,
            "data": {
                "total": total,
                "by_status": status_count,
                "score_stats": score_stats
            }
        }
    except Exception as e:
        logger.error(f"Erro ao obter distribuicao de scores: {e}")
        return {"success": False, "error": str(e)}

@debug_router.post("/limit-to-50")
def limit_to_50_best():
    """Keeps only 50 clinics with best score, moves rest to inactive."""
    if not supabase:
        return {"success": False, "error": "Supabase not configured"}
    
    try:
        # Get all clinics with score
        result = supabase.table("clinicas").select("id,nome,score,status").execute()
        clinicas = result.data or []
        
        if not clinicas:
            return {"success": True, "message": "No clinics found"}
        
        # Sort by score descending (None as 0)
        clinicas_sorted = sorted(
            clinicas, 
            key=lambda c: c.get('score') or 0, 
            reverse=True
        )
        
        total = len(clinicas_sorted)
        if total <= 50:
            return {
                "success": True, 
                "message": f"Already have {total} clinics (<= 50), no action needed"
            }
        
        # Top 50 stay active (set to qualified if not already)
        top_50 = clinicas_sorted[:50]
        restantes = clinicas_sorted[50:]
        
        # Update top 50 to qualified
        updated_top_50 = 0
        for clinica in top_50:
            if clinica.get('status') != 'qualificado':
                supabase.table("clinicas").update({"status": "qualificado"}).eq("id", clinica["id"]).execute()
                updated_top_50 += 1
        
        # Update rest to inactive
        updated_inativos = 0
        for clinica in restantes:
            if clinica.get('status') != 'inativo':
                supabase.table("clinicas").update({"status": "inativo"}).eq("id", clinica["id"]).execute()
                updated_inativos += 1
        
        logger.info(f"Limited clinics to 50 best score: {updated_top_50} updated to qualified, {updated_inativos} set to inactive")
        
        return {
            "success": True,
            "data": {
                "total_clinicas": total,
                "mantidas_ativas": 50,
                "movidas_para_inativo": len(restantes),
                "atualizadas_para_qualificado": updated_top_50,
                "definidas_como_inativo": updated_inativos
            }
        }
    except Exception as e:
        logger.error(f"Erro ao limitar clinicas: {e}")
        return {"success": False, "error": str(e)}

# Function to include this router in main app
def include_debug_router(app):
    app.include_router(debug_router)