/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ClearSpendCharts extends Component {
    static template = "clearspend.ChartsTemplate";
    static props = ["*"];
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            loading: true,
            data: null,
            error: null,
        });
        
        this.evolutionChartRef = useRef("evolutionChart");
        this.categoryChartRef = useRef("categoryChart");
        this.providersChartRef = useRef("providersChart");
        this.cycleChartRef = useRef("cycleChart");
        
        this.charts = [];
        
        onMounted(async () => {
            await this.loadChartJS();
            await this.loadData();
        });
        
        onWillUnmount(() => {
            this.destroyCharts();
        });
    }
    
    async loadChartJS() {
        // Charger Chart.js depuis CDN si pas déjà chargé
        if (typeof Chart === 'undefined') {
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
        }
    }
    
    async loadData() {
        try {
            this.state.loading = true;
            
            // Récupérer les données via RPC
            const data = await this.orm.call(
                "clearspend.dashboard",
                "get_charts_data",
                []
            );
            
            this.state.data = data;
            this.state.loading = false;
            
            // Attendre le prochain tick pour que le DOM soit prêt
            await new Promise(resolve => setTimeout(resolve, 100));
            
            this.renderCharts();
            
        } catch (error) {
            console.error("Erreur chargement données:", error);
            this.state.error = error.message || "Erreur lors du chargement des données";
            this.state.loading = false;
        }
    }
    
    destroyCharts() {
        this.charts.forEach(chart => {
            if (chart) chart.destroy();
        });
        this.charts = [];
    }
    
    renderCharts() {
        this.destroyCharts();
        
        const data = this.state.data;
        if (!data) return;
        
        // Graphique 1: Évolution des coûts (Line)
        const evolutionCtx = this.evolutionChartRef.el?.getContext('2d');
        if (evolutionCtx) {
            this.charts.push(new Chart(evolutionCtx, {
                type: 'line',
                data: {
                    labels: data.evolution.labels,
                    datasets: [{
                        label: 'Coût mensuel (€)',
                        data: data.evolution.values,
                        borderColor: '#3eb8a5',
                        backgroundColor: 'rgba(62, 184, 165, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#3eb8a5',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.parsed.y.toLocaleString('fr-FR')} €`
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => value.toLocaleString('fr-FR') + ' €'
                            }
                        }
                    }
                }
            }));
        }
        
        // Graphique 2: Répartition par catégorie (Doughnut)
        const categoryCtx = this.categoryChartRef.el?.getContext('2d');
        if (categoryCtx) {
            this.charts.push(new Chart(categoryCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Essentiels', 'Importants', 'Optionnels', 'À revoir'],
                    datasets: [{
                        data: [
                            data.categories.essential,
                            data.categories.important,
                            data.categories.optional,
                            data.categories.to_review
                        ],
                        backgroundColor: ['#dc3545', '#fd7e14', '#ffc107', '#6c757d'],
                        borderWidth: 3,
                        borderColor: '#fff',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '60%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { padding: 20 }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.label}: ${ctx.parsed.toLocaleString('fr-FR')} €`
                            }
                        }
                    }
                }
            }));
        }
        
        // Graphique 3: Top fournisseurs (Bar horizontal)
        const providersCtx = this.providersChartRef.el?.getContext('2d');
        if (providersCtx) {
            this.charts.push(new Chart(providersCtx, {
                type: 'bar',
                data: {
                    labels: data.providers.names,
                    datasets: [{
                        label: 'Coût mensuel (€)',
                        data: data.providers.values,
                        backgroundColor: [
                            '#1e3d5c', '#3eb8a5', '#2d5a87', '#5fcfbc', '#152a3d',
                            '#7dd4c7', '#4a7a9c', '#9ae5db', '#3d6b8a', '#b5f0e8'
                        ],
                        borderRadius: 8,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.parsed.x.toLocaleString('fr-FR')} €/mois`
                            }
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => value.toLocaleString('fr-FR') + ' €'
                            }
                        }
                    }
                }
            }));
        }
        
        // Graphique 4: Répartition par cycle (Pie)
        const cycleCtx = this.cycleChartRef.el?.getContext('2d');
        if (cycleCtx) {
            this.charts.push(new Chart(cycleCtx, {
                type: 'pie',
                data: {
                    labels: ['Mensuel', 'Trimestriel', 'Annuel'],
                    datasets: [{
                        data: [
                            data.cycles.monthly,
                            data.cycles.quarterly,
                            data.cycles.yearly
                        ],
                        backgroundColor: ['#3eb8a5', '#1e3d5c', '#5fcfbc'],
                        borderWidth: 3,
                        borderColor: '#fff',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { padding: 20 }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.label}: ${ctx.parsed} abonnements`
                            }
                        }
                    }
                }
            }));
        }
    }
    
    async refreshData() {
        await this.loadData();
    }
    
    goToDashboard() {
        this.action.doAction("clearspend.action_dashboard");
    }
    
    goToSubscriptions() {
        this.action.doAction("clearspend.action_subscription");
    }
}

// Enregistrer le composant comme action client
registry.category("actions").add("clearspend_charts", ClearSpendCharts);

export default ClearSpendCharts;
