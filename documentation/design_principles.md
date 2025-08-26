



## API

- endpoints are thin wrappers. They either delegate directly to a module, or combine multiple calls to modules to get the job done. They do not contain extensive business models themselves (simple logic is ok)
- endpoints must never manipulate databases directly
- authentication is handled in this layer
- api/endpoints/ stores the endpoints, api/types/ stores the api's DTO's


## Modules

- name_of_module/client.py contains the methods that are used elsewhere in the code (either by the api or by other modules)
- ORM models go into name_of_module/models.py and can also be imported elsewhere in the code (either by the api or by other modules)
- name_of_module/internals/ contains internal helper files


## shared/

- here, simple logic that doesn't depend on anything else goes
- examples: interaction with openrouter goes into shared/openrouter/client.py, interaction with arxiv goes into shared/arxiv/client.py 