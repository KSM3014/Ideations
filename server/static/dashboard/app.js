const { createApp, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    const batches = ref([]);
    const stats = ref(null);
    const curationState = ref({});
    const loading = ref(true);
    const toast = ref('');
    const refreshedAt = ref(new Date().toISOString());

    const gradeFilter = ref('');
    const curationFilter = ref('');
    const searchQuery = ref('');

    // All ideas flat list
    const allIdeas = computed(() => {
      const ideas = [];
      for (const batch of batches.value) {
        for (const idea of (batch.ideas || [])) {
          const uid = idea.id || idea.hypothesis_id || `${batch.batch_id}-${ideas.length}`;
          ideas.push({ ...idea, _uid: uid, _batch_id: batch.batch_id, _batch_ts: batch.timestamp });
        }
      }
      ideas.sort((a, b) => (b.weighted_score || b.numrv_score || 0) - (a.weighted_score || a.numrv_score || 0));
      return ideas;
    });

    function getCuration(idea) {
      const id = idea.id || idea.hypothesis_id || '';
      const entry = curationState.value[id];
      return entry ? entry.status : '';
    }

    const filteredIdeas = computed(() => {
      let result = allIdeas.value;

      if (gradeFilter.value) {
        result = result.filter(i => i.grade === gradeFilter.value);
      }

      if (curationFilter.value) {
        if (curationFilter.value === 'uncurated') {
          result = result.filter(i => !getCuration(i));
        } else {
          result = result.filter(i => getCuration(i) === curationFilter.value);
        }
      }

      if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        result = result.filter(i =>
          (i.service_name || '').toLowerCase().includes(q) ||
          (i.problem || '').toLowerCase().includes(q) ||
          (i.concept || i.solution || '').toLowerCase().includes(q)
        );
      }

      return result;
    });

    function formatTime(isoStr) {
      if (!isoStr) return '-';
      return new Date(isoStr).toLocaleString('ko-KR');
    }

    function showToast(msg) {
      toast.value = msg;
      setTimeout(() => { toast.value = ''; }, 3000);
    }

    async function fetchBatches() {
      try {
        const resp = await fetch('/api/batches');
        batches.value = await resp.json();
      } catch (e) {
        console.error('Failed to fetch batches:', e);
      } finally {
        loading.value = false;
      }
    }

    async function fetchStats() {
      try {
        const resp = await fetch('/api/curation/stats');
        stats.value = await resp.json();
      } catch (e) {
        console.error('Failed to fetch stats:', e);
      }
    }

    async function fetchAll() {
      await Promise.all([fetchBatches(), fetchStats()]);
      refreshedAt.value = new Date().toISOString();
      showToast('Refreshed');
    }

    async function setCuration(idea, status) {
      const id = idea.id || idea.hypothesis_id;
      if (!id) return;

      const current = getCuration(idea);
      const newStatus = current === status ? 'none' : status;

      try {
        await fetch(`/api/curation/${encodeURIComponent(id)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus }),
        });

        if (newStatus === 'none') {
          delete curationState.value[id];
        } else {
          curationState.value[id] = { status: newStatus };
        }
        fetchStats();
      } catch (e) {
        showToast('Failed to update curation');
      }
    }

    async function resetCuration() {
      if (!confirm('Reset all curation state?')) return;
      try {
        await fetch('/api/curation', { method: 'DELETE' });
        curationState.value = {};
        fetchStats();
        showToast('Curation reset');
      } catch (e) {
        showToast('Failed to reset');
      }
    }

    async function copyPublishedMD() {
      try {
        const resp = await fetch('/api/curation/export/md');
        const data = await resp.json();
        await navigator.clipboard.writeText(data.markdown);
        showToast(`Copied ${data.count} published ideas to clipboard`);
      } catch (e) {
        showToast('Failed to copy');
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
        showToast(`Feedback: ${action}`);
      } catch (e) {
        showToast('Feedback failed');
      }
    }

    onMounted(() => {
      fetchAll();
      setInterval(fetchAll, 5 * 60 * 1000);
    });

    return {
      batches, stats, loading, toast, refreshedAt,
      gradeFilter, curationFilter, searchQuery,
      allIdeas, filteredIdeas, getCuration, curationState,
      formatTime, fetchAll, setCuration, resetCuration,
      copyPublishedMD, sendFeedback, showToast,
    };
  }
}).mount('#app');
