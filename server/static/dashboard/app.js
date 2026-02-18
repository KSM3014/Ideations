const { createApp, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    const batches = ref([]);
    const health = ref(null);
    const loading = ref(true);
    const gradeFilter = ref('');
    const dateFilter = ref('');
    const searchQuery = ref('');

    const allIdeas = computed(() => {
      const ideas = [];
      for (const batch of batches.value) {
        for (const idea of (batch.ideas || [])) {
          ideas.push({ ...idea, batch_id: batch.batch_id, batch_timestamp: batch.timestamp });
        }
      }
      return ideas;
    });

    const filteredIdeas = computed(() => {
      let result = allIdeas.value;
      if (gradeFilter.value) {
        result = result.filter(i => i.grade === gradeFilter.value);
      }
      if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        result = result.filter(i =>
          (i.service_name || '').toLowerCase().includes(q) ||
          (i.problem || '').toLowerCase().includes(q) ||
          (i.concept || i.solution || '').toLowerCase().includes(q)
        );
      }
      // 점수 내림차순
      result.sort((a, b) => (b.numrv_score || b.weighted_score || 0) - (a.numrv_score || a.weighted_score || 0));
      return result;
    });

    const gradeDist = computed(() => {
      const dist = {};
      for (const idea of allIdeas.value) {
        const g = idea.grade || '?';
        dist[g] = (dist[g] || 0) + 1;
      }
      return dist;
    });

    function formatTime(isoStr) {
      if (!isoStr) return '';
      const d = new Date(isoStr);
      return d.toLocaleString('ko-KR');
    }

    async function fetchBatches() {
      try {
        const params = new URLSearchParams();
        if (dateFilter.value) params.set('date', dateFilter.value);
        const resp = await fetch(`/api/batches?${params}`);
        batches.value = await resp.json();
      } catch (e) {
        console.error('Failed to fetch batches:', e);
      } finally {
        loading.value = false;
      }
    }

    async function fetchHealth() {
      try {
        const resp = await fetch('/api/health');
        health.value = await resp.json();
      } catch (e) {
        console.error('Failed to fetch health:', e);
      }
    }

    async function sendFeedback(idea, action) {
      const id = idea.id || idea.hypothesis_id;
      try {
        await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hypothesis_id: id, action }),
        });
        alert(`피드백 전송 완료: ${action}`);
      } catch (e) {
        console.error('Feedback failed:', e);
      }
    }

    onMounted(() => {
      fetchBatches();
      fetchHealth();
      // 5분마다 갱신
      setInterval(fetchBatches, 5 * 60 * 1000);
      setInterval(fetchHealth, 60 * 1000);
    });

    return {
      batches, health, loading,
      gradeFilter, dateFilter, searchQuery,
      filteredIdeas, gradeDist,
      formatTime, sendFeedback,
    };
  }
}).mount('#app');
