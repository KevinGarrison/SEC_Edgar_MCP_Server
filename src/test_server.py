from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import AuthKitProvider


auth_provider = AuthKitProvider(
    authkit_domain='https://cultured-flower-34-staging.authkit.app',
    base_url="http://localhost:8080" 
)

mcp = FastMCP(name="AuthKit Secured App", auth=auth_provider, host='localhost',port=8080)


if __name__ == "__main__":
    mcp.run(transport='streamable-http')
