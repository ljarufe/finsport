for (const detail of document.querySelectorAll('.match-detail[data-url]')) {
  detail.addEventListener('toggle', async () => {
    if (!detail.open || detail.dataset.loaded === 'true') return;
    const target = detail.querySelector('.detail-content');
    try {
      const response = await fetch(detail.dataset.url, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      target.innerHTML = await response.text();
      detail.dataset.loaded = 'true';
    } catch (_error) {
      target.textContent = 'No se pudo cargar el detalle. Cierra y vuelve a abrirlo para reintentar.';
    }
  });
}
