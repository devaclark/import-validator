import aiofiles

class AsyncFileSystem:
    async def read_file(self, path: str) -> str:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return await f.read() 