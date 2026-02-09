from setuptools import setup, find_packages

setup(
    name="mcp-universal-crawler",
    version="0.1.0",
    description="MCP server exposing Futurepedia crawler tools",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "mcp>=1.2.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "pypdf>=5.0.0",
        "python-docx>=1.1.0",
    ],
)
