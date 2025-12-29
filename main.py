from fastmcp import FastMCP
import random
import json 

#Create a FastMCP Server instance 
mcp = FastMCP('Simple calculator server')

#Tool :Add two numbers
@mcp.tool
def add(a:int, b:int) -> int:
    '''Add two numbers together 
        Args:
            a:First number 
            b:Second number 

        Returns:
            The sum of a and b
    '''
    return a+b 

#Tool: Generate a random number 
@mcp.tool
def random_number(min_val:int=1, max_val:int=100) -> int:
    '''Generate a random number within a range 

    Args:
        min_val:Minimum values 
        max_val:Maximum values

    Returns 
        A random integer value between min_val and max_val 
    '''

    return random.randint(min_val,max_val)


#Resource:Server information 
@mcp.resource('info://server')
def server_info() -> str:
    '''Get information about this server'''
    info = {
    'name':'Simple calculator server',
    'version':'1.0.0',
    'description':'A basic MCP Server with math tools',
    'tools':['add','random_number'],
    'author':'Smaran'
}
    return json.dumps(info, indent=2)

#Start the server 
if __name__ == '__main__':
    mcp.run(transport='http',host='0.0.0.0',port=8000)