/* CRM Social Extension - Frontend JavaScript - Complete Version */

(function() {
    'use strict';

    // Customer Search Functionality
    class CustomerSearch {
        constructor() {
            this.searchInput = document.getElementById('search');
            this.suggestionsContainer = document.getElementById('search-suggestions');
            this.searchTimeout = null;
            this.minSearchLength = 2;
            
            this.init();
        }

        init() {
            if (!this.searchInput || !this.suggestionsContainer) {
                return;
            }

            this.searchInput.addEventListener('input', this.handleSearchInput.bind(this));
            this.searchInput.addEventListener('focus', this.handleSearchFocus.bind(this));
            this.searchInput.addEventListener('blur', this.handleSearchBlur.bind(this));
            
            // Close suggestions when clicking outside
            document.addEventListener('click', this.handleDocumentClick.bind(this));
            
            // Handle keyboard navigation
            this.searchInput.addEventListener('keydown', this.handleKeyDown.bind(this));
        }

        handleSearchInput(event) {
            const searchTerm = event.target.value.trim();
            
            // Clear previous timeout
            if (this.searchTimeout) {
                clearTimeout(this.searchTimeout);
            }

            if (searchTerm.length < this.minSearchLength) {
                this.hideSuggestions();
                return;
            }

            // Debounce search requests
            this.searchTimeout = setTimeout(() => {
                this.performSearch(searchTerm);
            }, 300);
        }

        handleSearchFocus(event) {
            const searchTerm = event.target.value.trim();
            if (searchTerm.length >= this.minSearchLength) {
                this.performSearch(searchTerm);
            }
        }

        handleSearchBlur(event) {
            // Delay hiding to allow clicking on suggestions
            setTimeout(() => {
                this.hideSuggestions();
            }, 200);
        }

        handleDocumentClick(event) {
            if (!this.searchInput.contains(event.target) && 
                !this.suggestionsContainer.contains(event.target)) {
                this.hideSuggestions();
            }
        }

        handleKeyDown(event) {
            const suggestions = this.suggestionsContainer.querySelectorAll('.list-group-item');
            const currentActive = this.suggestionsContainer.querySelector('.list-group-item.active');
            
            switch(event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    this.navigateSuggestions(suggestions, currentActive, 'down');
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    this.navigateSuggestions(suggestions, currentActive, 'up');
                    break;
                case 'Enter':
                    if (currentActive) {
                        event.preventDefault();
                        currentActive.click();
                    }
                    break;
                case 'Escape':
                    this.hideSuggestions();
                    break;
            }
        }

        navigateSuggestions(suggestions, currentActive, direction) {
            if (suggestions.length === 0) return;

            // Remove current active class
            if (currentActive) {
                currentActive.classList.remove('active');
            }

            let nextIndex = 0;
            if (currentActive) {
                const currentIndex = Array.from(suggestions).indexOf(currentActive);
                if (direction === 'down') {
                    nextIndex = (currentIndex + 1) % suggestions.length;
                } else {
                    nextIndex = currentIndex === 0 ? suggestions.length - 1 : currentIndex - 1;
                }
            }

            suggestions[nextIndex].classList.add('active');
            suggestions[nextIndex].scrollIntoView({ block: 'nearest' });
        }

        async performSearch(searchTerm) {
            try {
                this.showLoadingState();
                
                const response = await fetch('/customers/search/autocomplete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        method: 'call',
                        params: { term: searchTerm }
                    })
                });

                const data = await response.json();
                const results = data.result || [];
                
                this.displaySuggestions(results);
            } catch (error) {
                console.error('Search error:', error);
                this.hideSuggestions();
            }
        }

        showLoadingState() {
            this.suggestionsContainer.innerHTML = `
                <div class="list-group-item text-center">
                    <div class="loading-spinner"></div>
                    <span class="ms-2">Searching...</span>
                </div>
            `;
            this.suggestionsContainer.style.display = 'block';
        }

        displaySuggestions(results) {
            if (results.length === 0) {
                this.suggestionsContainer.innerHTML = `
                    <div class="list-group-item text-muted text-center">
                        <i class="fa fa-search me-2"></i>
                        No customers found
                    </div>
                `;
            } else {
                this.suggestionsContainer.innerHTML = results.map(result => {
                    const platformIcons = result.social_platforms.map(platform => {
                        const iconMap = {
                            'Facebook': 'fa-facebook facebook-color',
                            'LinkedIn': 'fa-linkedin linkedin-color',
                            'Twitter': 'fa-twitter twitter-color'
                        };
                        return `<i class="fa ${iconMap[platform]} me-1" title="${platform}"></i>`;
                    }).join('');

                    const completeBadge = result.is_complete 
                        ? '<span class="badge bg-success ms-2">Complete</span>'
                        : '<span class="badge bg-warning ms-2">Incomplete</span>';

                    return `
                        <a href="${result.url}" class="list-group-item list-group-item-action">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <div class="suggestion-name">${result.name}</div>
                                    <div class="suggestion-platforms">
                                        ${platformIcons}
                                        ${result.social_platforms.join(', ') || 'No social media'}
                                    </div>
                                </div>
                                <div class="text-end">
                                    <div class="suggestion-score">
                                        <span class="badge bg-primary">Score: ${result.social_score}</span>
                                        ${completeBadge}
                                    </div>
                                </div>
                            </div>
                        </a>
                    `;
                }).join('');
            }
            
            this.suggestionsContainer.style.display = 'block';
        }

        hideSuggestions() {
            this.suggestionsContainer.style.display = 'none';
        }
    }

    // Customer Statistics Dashboard
    class CustomerStats {
        constructor() {
            this.statsContainer = document.querySelector('.stats-section');
            this.init();
        }

        init() {
            if (this.statsContainer) {
                this.loadStats();
            }
        }

        async loadStats() {
            try {
                const response = await fetch('/customers/api/stats', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        method: 'call',
                        params: {}
                    })
                });

                const data = await response.json();
                const stats = data.result || {};
                
                this.updateStatsDisplay(stats);
            } catch (error) {
                console.error('Stats loading error:', error);
            }
        }

        updateStatsDisplay(stats) {
            // Update completion rate if element exists
            const completionRateElement = document.querySelector('[data-stat="completion-rate"]');
            if (completionRateElement) {
                completionRateElement.textContent = `${stats.completion_rate}%`;
            }

            // Update platform statistics
            Object.entries(stats.platform_stats || {}).forEach(([platform, count]) => {
                const element = document.querySelector(`[data-stat="${platform}"]`);
                if (element) {
                    element.textContent = count;
                }
            });
        }
    }

    // Card Animations and Interactions
    class CardInteractions {
        constructor() {
            this.init();
        }

        init() {
            this.initCardHoverEffects();
            this.initSocialLinkTracking();
            this.initLazyLoading();
        }

        initCardHoverEffects() {
            const cards = document.querySelectorAll('.customer-card');
            
            cards.forEach(card => {
                card.addEventListener('mouseenter', this.handleCardHover.bind(this));
                card.addEventListener('mouseleave', this.handleCardLeave.bind(this));
            });
        }

        handleCardHover(event) {
            const card = event.currentTarget;
            card.style.transform = 'translateY(-8px)';
            card.style.boxShadow = '0 12px 30px rgba(0, 0, 0, 0.15)';
        }

        handleCardLeave(event) {
            const card = event.currentTarget;
            card.style.transform = 'translateY(0)';
            card.style.boxShadow = '';
        }

        initSocialLinkTracking() {
            const socialLinks = document.querySelectorAll('.social-links a, .social-icon a');
            
            socialLinks.forEach(link => {
                link.addEventListener('click', this.trackSocialClick.bind(this));
            });
        }

        trackSocialClick(event) {
            const link = event.currentTarget;
            const platform = this.getSocialPlatform(link.href);
            
            // Track social media clicks (can be extended with analytics)
            console.log(`Social link clicked: ${platform}`);
            
            // Add visual feedback
            link.style.transform = 'scale(0.95)';
            setTimeout(() => {
                link.style.transform = '';
            }, 150);
        }

        getSocialPlatform(url) {
            if (url.includes('facebook.com')) return 'Facebook';
            if (url.includes('linkedin.com')) return 'LinkedIn';
            if (url.includes('twitter.com') || url.includes('x.com')) return 'Twitter';
            return 'Unknown';
        }

        initLazyLoading() {
            const images = document.querySelectorAll('img[data-src]');
            
            if ('IntersectionObserver' in window) {
                const imageObserver = new IntersectionObserver((entries, observer) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            img.src = img.dataset.src;
                            img.classList.remove('lazy');
                            imageObserver.unobserve(img);
                        }
                    });
                });

                images.forEach(img => imageObserver.observe(img));
            }
        }
    }

    // Filter and Sort Functionality
    class FilterSort {
        constructor() {
            this.filterForm = document.querySelector('form[action="/customers"]');
            this.init();
        }

        init() {
            if (this.filterForm) {
                this.initFilterForm();
                this.initUrlParams();
            }
        }

        initFilterForm() {
            const selects = this.filterForm.querySelectorAll('select');
            selects.forEach(select => {
                select.addEventListener('change', this.handleFilterChange.bind(this));
            });
        }

        initUrlParams() {
            const urlParams = new URLSearchParams(window.location.search);
            
            // Restore form values from URL
            urlParams.forEach((value, key) => {
                const input = this.filterForm.querySelector(`[name="${key}"]`);
                if (input) {
                    input.value = value;
                }
            });
        }

        handleFilterChange(event) {
            // Auto-submit form when filter changes
            setTimeout(() => {
                this.filterForm.submit();
            }, 100);
        }
    }

    // Utility Functions
    const Utils = {
        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        throttle(func, limit) {
            let inThrottle;
            return function() {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },

        showToast(message, type = 'info') {
            // Simple toast notification
            const toast = document.createElement('div');
            toast.className = `alert alert-${type} position-fixed`;
            toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
            toast.innerHTML = `
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                ${message}
            `;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 5000);
        }
    };

    // Initialize everything when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        console.log('CRM Social Extension frontend JS loading...');
        
        try {
            // Initialize all components
            new CustomerSearch();
            new CustomerStats();
            new CardInteractions();
            new FilterSort();

            // Add smooth scrolling to anchor links
            document.querySelectorAll('a[href^="#"]').forEach(anchor => {
                anchor.addEventListener('click', function (e) {
                    e.preventDefault();
                    const target = document.querySelector(this.getAttribute('href'));
                    if (target) {
                        target.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    }
                });
            });

            // Add loading states to buttons
            document.querySelectorAll('form').forEach(form => {
                form.addEventListener('submit', function() {
                    const submitBtn = form.querySelector('button[type="submit"]');
                    if (submitBtn) {
                        submitBtn.innerHTML = '<span class="loading-spinner me-2"></span>Loading...';
                        submitBtn.disabled = true;
                    }
                });
            });

            // Initialize tooltips if Bootstrap is available
            if (typeof bootstrap !== 'undefined') {
                const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
                tooltipTriggerList.map(function (tooltipTriggerEl) {
                    return new bootstrap.Tooltip(tooltipTriggerEl);
                });
            }

            console.log('CRM Social Extension frontend JS loaded successfully');
        } catch (error) {
            console.error('Error loading CRM Social Extension frontend JS:', error);
        }
    });

    // Make utilities available globally
    window.CRMSocialUtils = Utils;

})();