// AGENTX Decision Log — inject nav link into sidebar
(function(){
  function injectNav() {
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (!sidebarNav) return;
    
    // Check if already injected
    if (sidebarNav.querySelector('[data-decision-log]')) return;
    
    // Find the AI Orchestrator or Settings nav item to insert before
    const settingsItem = sidebarNav.querySelector('.nav-item:last-child');
    const insertBefore = sidebarNav.querySelector('.nav-item:nth-child(9)') || settingsItem;
    
    const newItem = document.createElement('div');
    newItem.className = 'nav-item';
    newItem.setAttribute('data-decision-log', 'true');
    
    // Check if current page is decision-log
    if (window.location.pathname.includes('decision-log')) {
      newItem.classList.add('active');
    }
    
    newItem.innerHTML = '<span class="icon">✦</span><a href="/decision-log.html">Decision Log</a>';
    
    sidebarNav.insertBefore(newItem, insertBefore);
  }
  
  // Run on DOMContentLoaded and periodically (for React re-renders)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectNav);
  } else {
    injectNav();
  }
  setTimeout(injectNav, 1000);
  setTimeout(injectNav, 3000);
})();
