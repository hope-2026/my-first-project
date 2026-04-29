exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  try {
    const body = JSON.parse(event.body);
    // Force non-streaming to avoid OpenRouter stream idle timeout
    const requestBody = { ...body, stream: false };

    let data;
    let lastError;

    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + process.env.OPENROUTER_API_KEY,
            'HTTP-Referer': process.env.URL || 'https://localhost',
          },
          body: JSON.stringify(requestBody),
          signal: AbortSignal.timeout(22000),
        });

        data = await response.json();

        // Retry on stream idle timeout error
        const errMsg = data.error && data.error.message ? data.error.message : '';
        if (errMsg.toLowerCase().includes('stream idle timeout') || errMsg.toLowerCase().includes('partial response')) {
          lastError = errMsg;
          continue;
        }

        break;
      } catch (fetchErr) {
        lastError = fetchErr.message;
        if (attempt < 2) continue;
        throw fetchErr;
      }
    }

    if (!data) {
      data = { error: { message: lastError || 'Unbekannter Fehler' } };
    }

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    };
  } catch (e) {
    const isTimeout = e.name === 'TimeoutError' || e.name === 'AbortError';
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: { message: isTimeout ? 'Zeitüberschreitung - bitte nochmal versuchen' : e.message }
      }),
    };
  }
};
