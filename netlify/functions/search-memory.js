exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  try {
    const { query, max_results = 5 } = JSON.parse(event.body);
    const vectorStoreId = process.env.MEMORY_VECTOR_STORE_ID;
    const apiKey = process.env.OPENAI_API_KEY;

    if (!vectorStoreId) {
      return {
        statusCode: 503,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: { message: 'Memory nicht konfiguriert' } }),
      };
    }

    const response = await fetch(
      `https://api.openai.com/v1/vector_stores/${vectorStoreId}/search`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + apiKey,
          'OpenAI-Beta': 'assistants=v2',
        },
        body: JSON.stringify({ query, max_num_results: max_results }),
      }
    );

    const data = await response.json();

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    };
  } catch (e) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: { message: e.message } }),
    };
  }
};
