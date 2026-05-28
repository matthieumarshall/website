(function () {
  'use strict';

  function balanceTabNav(nav) {
    var container = nav.querySelector('[role="group"]');
    if (!container) return;
    var buttons = Array.from(container.querySelectorAll('button'));
    if (buttons.length <= 1) return;

    // Reset any sizing from a previous run so offsetWidth reflects natural size.
    buttons.forEach(function (b) {
      b.style.flexBasis = '';
      b.style.flexGrow = '';
      b.style.flexShrink = '';
    });

    var gap = parseFloat(getComputedStyle(container).columnGap) || 0;
    var containerWidth = container.clientWidth;

    // Simulate natural flex-wrap to count how many rows form.
    var rows = 1;
    var rowWidth = 0;
    buttons.forEach(function (btn) {
      var w = btn.offsetWidth;
      var needed = rowWidth > 0 ? rowWidth + gap + w : w;
      if (rowWidth > 0 && needed > containerWidth) {
        rows++;
        rowWidth = w;
      } else {
        rowWidth = needed;
      }
    });

    if (rows <= 1) return;

    // Distribute evenly: ceil(n / rows) buttons per row.
    var cols = Math.ceil(buttons.length / rows);
    var btnW = Math.floor((containerWidth - gap * (cols - 1)) / cols);
    buttons.forEach(function (b) {
      b.style.flexBasis = btnW + 'px';
      b.style.flexGrow = '0';
      b.style.flexShrink = '0';
    });
  }

  function balanceAll() {
    document.querySelectorAll('nav.standings-tab-nav').forEach(balanceTabNav);
  }

  function resetAll() {
    document.querySelectorAll('nav.standings-tab-nav [role="group"] button').forEach(function (b) {
      b.style.flexBasis = '';
      b.style.flexGrow = '';
      b.style.flexShrink = '';
    });
  }

  document.addEventListener('DOMContentLoaded', balanceAll);

  // Re-balance after HTMX swaps in the category panel.
  document.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail && e.detail.target && e.detail.target.id === 'category-panel') {
      requestAnimationFrame(balanceAll);
    }
  });

  // Re-balance on window resize (debounced).
  var resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      resetAll();
      requestAnimationFrame(balanceAll);
    }, 100);
  });
}());
