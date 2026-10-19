"""A plugin written for another plugin API: the gateway must not run it."""


def setup(context):
    async def handle_hello(request):
        return context.json({"plugin": context.id})

    context.add_get("/hello", handle_hello)
