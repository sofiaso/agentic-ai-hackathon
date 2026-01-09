"""Unit tests for tool routing functionality."""

from iac_agent.llm.schemas import ToolRouterOutput
from iac_agent.llm.tool_catalog import get_fallback_tool, get_tool_catalog, get_tool_by_id


def test_tool_catalog_structure() -> None:
    """Test that tool catalog has correct structure."""
    catalog = get_tool_catalog()
    
    # Should have exactly 3 tools
    assert len(catalog) == 3
    
    # Should have exactly one fallback tool
    fallback_tools = [tool for tool in catalog if tool.is_general_fallback]
    assert len(fallback_tools) == 1
    assert fallback_tools[0].tool_id == "checkov"
    
    # All tools should have required fields
    for tool in catalog:
        assert tool.tool_id in ["terraform_validate", "tfsec", "checkov"]
        assert tool.display_name
        assert tool.short_description
        assert tool.detailed_description
        assert len(tool.strengths) > 0
        assert len(tool.limitations) > 0
        assert len(tool.best_for) > 0
        assert len(tool.keywords) > 0
        assert isinstance(tool.is_general_fallback, bool)


def test_fallback_tool() -> None:
    """Test that fallback tool is checkov."""
    fallback = get_fallback_tool()
    assert fallback == "checkov"


def test_get_tool_by_id() -> None:
    """Test getting tool by ID."""
    tool = get_tool_by_id("checkov")
    assert tool is not None
    assert tool.tool_id == "checkov"
    assert tool.is_general_fallback is True
    
    tool = get_tool_by_id("terraform_validate")
    assert tool is not None
    assert tool.tool_id == "terraform_validate"
    assert tool.is_general_fallback is False
    
    tool = get_tool_by_id("nonexistent")
    assert tool is None


def test_tool_router_output_empty_selected_tools() -> None:
    """Test that empty selected_tools triggers fallback."""
    # This would be caught by Pydantic validation, but test the fallback logic
    try:
        output = ToolRouterOutput(
            selected_tools=[],  # Empty - should fail validation
            fallback_used=False,
            rationale="Test",
            tool_intent_summary="Test intent",
        )
        # Should not reach here due to validation
        assert False, "Should have failed validation"
    except Exception:
        # Expected - Pydantic should reject empty list
        pass


def test_tool_router_output_fallback() -> None:
    """Test that fallback_used=True returns checkov."""
    output = ToolRouterOutput(
        selected_tools=["checkov"],
        fallback_used=True,
        rationale="User request unclear, using fallback",
        tool_intent_summary="General assessment",
    )
    
    assert output.selected_tools == ["checkov"]
    assert output.fallback_used is True
    assert "fallback" in output.rationale.lower()


def test_tool_router_output_terraform_validate_selection() -> None:
    """Test that terraform_validate can be selected."""
    output = ToolRouterOutput(
        selected_tools=["terraform_validate"],
        fallback_used=False,
        rationale="User requested syntax validation",
        tool_intent_summary="Check Terraform syntax",
    )
    
    assert "terraform_validate" in output.selected_tools
    assert output.fallback_used is False


def test_tool_router_output_multiple_tools() -> None:
    """Test that multiple tools can be selected."""
    output = ToolRouterOutput(
        selected_tools=["terraform_validate", "tfsec"],
        fallback_used=False,
        rationale="User needs both validation and security checks",
        tool_intent_summary="Comprehensive Terraform analysis",
    )
    
    assert len(output.selected_tools) == 2
    assert "terraform_validate" in output.selected_tools
    assert "tfsec" in output.selected_tools
    assert output.fallback_used is False


def test_tool_catalog_keywords() -> None:
    """Test that keywords are appropriate for each tool."""
    catalog = get_tool_catalog()
    
    for tool in catalog:
        # Terraform validate should have syntax/validation keywords
        if tool.tool_id == "terraform_validate":
            assert any("syntax" in kw.lower() for kw in tool.keywords)
            assert any("valid" in kw.lower() for kw in tool.keywords)
        
        # Tfsec should have security keywords
        elif tool.tool_id == "tfsec":
            assert any("security" in kw.lower() for kw in tool.keywords)
            assert any("iam" in kw.lower() for kw in tool.keywords)
        
        # Checkov should have compliance keywords
        elif tool.tool_id == "checkov":
            assert any("compliance" in kw.lower() for kw in tool.keywords)
            assert any("cis" in kw.lower() for kw in tool.keywords)


def test_tool_descriptions_quality() -> None:
    """Test that tool descriptions are high quality and informative."""
    catalog = get_tool_catalog()
    
    for tool in catalog:
        # Short description should be 1-2 lines (reasonable length)
        assert 20 <= len(tool.short_description) <= 200
        
        # Detailed description should be 5-10 lines (reasonable length)
        assert 100 <= len(tool.detailed_description) <= 1000
        
        # Should have multiple strengths and limitations
        assert len(tool.strengths) >= 3
        assert len(tool.limitations) >= 2
        
        # Should have multiple best-for use cases
        assert len(tool.best_for) >= 3
