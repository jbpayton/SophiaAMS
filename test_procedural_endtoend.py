"""
End-to-End Procedural Knowledge Test

Tests:
1. Diverse procedural knowledge ingestion (API, research, deployment, troubleshooting)
2. query_procedure retrieval
3. Multi-step hierarchical procedures
4. No example overlap with prompt
"""

import sys
import time
import os
import shutil
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph


def print_section(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_diverse_procedures():
    """Test with diverse, realistic multi-step procedures"""
    print_section("END-TO-END PROCEDURAL KNOWLEDGE TEST")

    test_db = "Test_EndToEnd_Procedural"
    if os.path.exists(test_db):
        shutil.rmtree(test_db)

    try:
        kgraph = VectorKnowledgeGraph(path=test_db)
        memory = AssociativeSemanticMemory(kgraph)

        # Test 1: Research procedure (finding information online)
        print_section("Test 1: Teaching Research Procedure")

        research_teaching = """
        To research a technical topic thoroughly:
        1. First, search academic papers on Google Scholar
        2. Then, check official documentation on the project website
        3. Finally, look for discussions on Stack Overflow or GitHub issues

        Searching Google Scholar requires using specific keywords and operators.
        Example: "machine learning" AND "neural networks" site:arxiv.org

        Alternatively, you can use Semantic Scholar for AI/CS topics.
        """

        print("Teaching text:")
        print(research_teaching[:200] + "...")

        result = memory.ingest_text(research_teaching, source="research_guide")
        print(f"\nExtracted {len(result['original_triples'])} triples")

        time.sleep(2)  # Allow indexing

        # Query for research procedure
        print("\nQuerying: 'research technical topic'")
        proc_result = memory.query_procedure("research technical topic", limit=15)

        print(f"\nFound {proc_result['total_found']} procedural facts:")
        print(f"  Methods: {len(proc_result['methods'])}")
        print(f"  Steps: {len(proc_result['steps'])}")
        print(f"  Alternatives: {len(proc_result['alternatives'])}")
        print(f"  Examples: {len(proc_result['examples'])}")

        # Validate
        has_results = proc_result['total_found'] > 0
        has_steps = len(proc_result['steps']) > 0

        print(f"\n[{'PASS' if has_results else 'FAIL'}] Found procedural knowledge")
        print(f"[{'PASS' if has_steps else 'FAIL'}] Extracted sequential steps")

        if proc_result['steps']:
            print("\nSample steps:")
            for triple, meta in proc_result['steps'][:3]:
                print(f"  - {triple[0]} -> {triple[2]}")

        # Test 2: Deployment procedure (multi-tool workflow)
        print_section("Test 2: Teaching Deployment Workflow")

        deployment_teaching = """
        To deploy a web application to production:

        First, you need to prepare the environment:
        - Set up a virtual environment using venv
        - Install dependencies with pip install -r requirements.txt

        Then, build the application:
        - Run the build script: npm run build
        - This requires Node.js to be installed first

        Next, configure the server:
        - Update nginx configuration at /etc/nginx/sites-available/
        - Restart nginx: sudo systemctl restart nginx

        Finally, deploy the code:
        - Use git pull origin main to get latest code
        - Restart the application service: sudo systemctl restart myapp

        Alternatively, you can use Docker for containerized deployment.
        Example: docker-compose up -d
        """

        print("Teaching deployment workflow...")
        result = memory.ingest_text(deployment_teaching, source="deployment_guide")
        print(f"Extracted {len(result['original_triples'])} triples")

        time.sleep(2)

        print("\nQuerying: 'deploy web application'")
        deploy_proc = memory.query_procedure("deploy web application", limit=20)

        print(f"\nFound {deploy_proc['total_found']} procedural facts:")
        print(f"  Methods: {len(deploy_proc['methods'])}")
        print(f"  Dependencies: {len(deploy_proc['dependencies'])}")
        print(f"  Alternatives: {len(deploy_proc['alternatives'])}")
        print(f"  Examples: {len(deploy_proc['examples'])}")

        has_deploy = deploy_proc['total_found'] > 0
        has_deps = len(deploy_proc['dependencies']) > 0

        print(f"\n[{'PASS' if has_deploy else 'FAIL'}] Found deployment procedures")
        print(f"[{'PASS' if has_deps else 'FAIL'}] Found dependencies")

        # Test 3: Troubleshooting procedure (conditional logic)
        print_section("Test 3: Teaching Troubleshooting Steps")

        troubleshoot_teaching = """
        To troubleshoot a connection error:

        First, check the basics:
        - Verify network connectivity: ping google.com
        - Check if the service is running: systemctl status myservice

        If the service is down, restart it:
        - Use: sudo systemctl restart myservice
        - Then verify: curl http://localhost:8080/health

        If connection still fails, check the logs:
        - View recent logs: tail -f /var/log/myservice/error.log
        - Look for error patterns like "connection refused" or "timeout"

        Alternatively, use netstat to check open ports:
        Example: netstat -tulpn | grep 8080

        This diagnostic process enables quick root cause identification.
        """

        print("Teaching troubleshooting procedure...")
        result = memory.ingest_text(troubleshoot_teaching, source="troubleshooting_guide")
        print(f"Extracted {len(result['original_triples'])} triples")

        time.sleep(2)

        print("\nQuerying: 'troubleshoot connection error'")
        troubleshoot_proc = memory.query_procedure("troubleshoot connection error", limit=20)

        print(f"\nFound {troubleshoot_proc['total_found']} procedural facts:")
        print(f"  Methods: {len(troubleshoot_proc['methods'])}")
        print(f"  Steps: {len(troubleshoot_proc['steps'])}")
        print(f"  Examples: {len(troubleshoot_proc['examples'])}")

        has_troubleshoot = troubleshoot_proc['total_found'] > 0

        print(f"\n[{'PASS' if has_troubleshoot else 'FAIL'}] Found troubleshooting procedures")

        if troubleshoot_proc['examples']:
            print("\nSample examples found:")
            for triple, meta in troubleshoot_proc['examples'][:2]:
                print(f"  - {triple[2]}")

        # Test 4: Cross-domain query (can it find related procedures?)
        print_section("Test 4: Cross-Domain Retrieval")

        print("\nQuerying: 'check if service is running'")
        service_check = memory.query_procedure("check if service is running", limit=10)

        print(f"Found {service_check['total_found']} related procedures")

        # Should find systemctl status from troubleshooting guide
        has_service_check = service_check['total_found'] > 0

        print(f"[{'PASS' if has_service_check else 'FAIL'}] Cross-domain retrieval works")

        # Test 5: Hierarchical query (high-level task decomposition)
        print_section("Test 5: Hierarchical Task Decomposition")

        # Query a high-level task that should decompose into learned procedures
        print("\nQuerying high-level: 'set up production environment'")
        setup_proc = memory.query_procedure("set up production environment", limit=20)

        print(f"Found {setup_proc['total_found']} related procedures")
        print(f"  Methods: {len(setup_proc['methods'])}")
        print(f"  Dependencies: {len(setup_proc['dependencies'])}")

        # Should find deployment-related procedures
        has_setup = setup_proc['total_found'] > 0

        print(f"[{'PASS' if has_setup else 'FAIL'}] High-level task retrieval works")

        # Summary
        print_section("TEST SUMMARY")

        tests = [
            ("Research procedure extraction & retrieval", has_results and has_steps),
            ("Deployment workflow with dependencies", has_deploy and has_deps),
            ("Troubleshooting procedure extraction", has_troubleshoot),
            ("Cross-domain procedure retrieval", has_service_check),
            ("Hierarchical task decomposition", has_setup),
        ]

        passed = sum(1 for _, result in tests if result)
        total = len(tests)

        for name, result in tests:
            status = "[PASS]" if result else "[FAIL]"
            print(f"{status} {name}")

        print(f"\n{passed}/{total} tests passed ({passed/total*100:.1f}%)")

        memory.close()
        time.sleep(2)

        if passed == total:
            print("\n*** ALL END-TO-END TESTS PASSED! ***")
            result_code = 0
        else:
            print(f"\n*** {total - passed} test(s) failed ***")
            result_code = 1

        # Cleanup
        time.sleep(2)  # Extra delay for file handles to close
        if os.path.exists(test_db):
            try:
                shutil.rmtree(test_db)
            except Exception as e:
                print(f"\nWarning: Could not clean up test database: {e}")

        return result_code

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(test_diverse_procedures())
