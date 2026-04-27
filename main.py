# -*- coding: utf-8 -*-
"""Core entrypoint for career planning pipeline."""
from __future__ import annotations

from config import AppConfig

AppConfig.ensure_dirs()


def load_job_data(path=None):
    from services.data_processor import load_job_data as _load

    return _load(path or AppConfig.JOB_DATA_PATH)


def initialize_system() -> tuple:
    """Initialize config, LLM wrapper, job profiles, graph and matcher."""
    from dotenv import load_dotenv

    load_dotenv()

    from models.llm_wrapper import LLMWrapper
    from models.job_profile import JobProfileBuilder
    from models.graph_builder import CareerGraphBuilder
    from models.matching_engine import MatchingEngine
    from services.data_processor import load_job_data as load_jobs

    llm = LLMWrapper(
        provider=AppConfig.LLM_PROVIDER,
        api_key=AppConfig.LLM_API_KEY,
        model_name=AppConfig.LLM_MODEL_NAME,
        base_url=AppConfig.LLM_BASE_URL,
    )
    # Fast startup: build rule-based job profiles by default.
    job_data = load_jobs(AppConfig.JOB_DATA_PATH)
    builder = JobProfileBuilder(llm=None)
    job_profiles = builder.batch_build_profiles(job_data)

    career_graph = CareerGraphBuilder()
    career_graph.build_vertical_path(job_profiles)
    career_graph.build_lateral_path(job_profiles)
    career_graph.export_graph(
        output_path=str(AppConfig.GRAPH_OUTPUT_PATH),
        json_path=str(AppConfig.GRAPH_JSON_PATH),
    )

    matching_engine = MatchingEngine(weights=AppConfig.MATCH_WEIGHTS, llm=llm)
    return llm, job_profiles, career_graph, matching_engine


def process_student_career_planning(student_input: dict, system_components: tuple) -> dict:
    """Run student profiling, matching, path planning and report generation."""
    llm, job_profiles, career_graph, matching_engine = system_components
    from models.student_profile import StudentProfileAnalyzer
    from models.report_generator import CareerReportGenerator

    analyzer = StudentProfileAnalyzer(llm=llm)
    mbti = (student_input.get("mbti_type") or "").strip()
    if student_input.get("resume_path"):
        student_profile = analyzer.analyze_from_resume(student_input["resume_path"], mbti_type=mbti)
    else:
        fd = dict(student_input.get("form_data") or {})
        if mbti:
            fd["mbti_type"] = mbti
        student_profile = analyzer.analyze_from_form(fd)

    top_k = student_input.get("top_k", 10)
    use_ai = bool(student_input.get("use_ai", False))
    match_results = matching_engine.recommend_top_jobs(
        student_profile, job_profiles, top_k=top_k, use_ai=use_ai
    )
    target_jobs = student_input.get("target_jobs") or []
    target_job = (match_results[0]["job_name"] if match_results else "") or (
        target_jobs[0] if target_jobs else ""
    )

    report_gen = CareerReportGenerator(llm_wrapper=llm)
    career_path = report_gen.generate_career_path_section(target_job, career_graph)
    top_match = match_results[0] if match_results else {}
    gap = top_match.get("gap_analysis", {})
    action_plan = report_gen.generate_action_plan(
        gap, target_job=target_job, top_match=top_match, timeline="6_months"
    )
    executive_summary = report_gen.generate_executive_summary(top_match)
    report_data = report_gen.compile_full_report(
        student_profile,
        match_results,
        career_path,
        action_plan,
        executive_summary=executive_summary,
    )
    return {
        "student_profile": student_profile,
        "match_results": match_results,
        "career_path": career_path,
        "action_plan": action_plan,
        "report_data": report_data,
    }


def main():
    """CLI demo."""
    print("Initializing system...")
    components = initialize_system()
    _, job_profiles, _, _ = components
    print(f"Loaded {len(job_profiles)} job profiles.")
    print("Run API: python api_server.py")


if __name__ == "__main__":
    main()

